"""
AMD Text Classifier
═══════════════════════════════════════════════════════════════════════════════

TF-IDF + Logistic Regression classifier for human vs machine detection.
Takes a transcript (from Whisper) and classifies it as "human" or "machine"
with a confidence score.

When no pre-trained model is available, falls back to a rule-based heuristic
that catches common voicemail phrases. The heuristic is intentionally simple —
it exists only to provide reasonable default behavior until a proper model
is trained on real campaign data.

Training a custom model:
  1. Collect transcripts with labels (human|machine) in CSV format
  2. Run: python -m classifier --train --csv data.csv --out models/text_cls.joblib
  3. Restart the sidecar service
"""

import logging
import os
import re
from pathlib import Path

import numpy as np

logger = logging.getLogger("whisper-amd.classifier")

# ── Common voicemail indicator phrases ────────────────────────────────────────
# These are used by the rule-based fallback when no trained model is available.
# They are NOT used when a joblib model is loaded — the model learns its own
# features from training data.
VM_PHRASES = [
    "leave a message",
    "leave your message",
    "leave your name",
    "after the tone",
    "after the beep",
    "at the tone",
    "not available",
    "not here right now",
    "can't come to the phone",
    "cannot come to the phone",
    "can't take your call",
    "cannot take your call",
    "please leave",
    "voicemail",
    "voice mail",
    "mailbox",
    "press 1",
    "press one",
    "menu options",
    "office hours",
    "business hours",
    "you have reached",
    "you've reached",
    "the person you are calling",
    "the party you are trying to reach",
    "is not available",
    "record your message",
    "recording",
]

# Short human greetings — if the entire transcript IS one of these, it's HUMAN
HUMAN_GREETINGS = [
    "hello",
    "hello?",
    "hi",
    "hey",
    "yeah",
    "yeah?",
    "yes",
    "yes?",
    "yo",
    "what's up",
    "who is this",
    "who's this",
    "speaking",
]


class AMDClassifier:
    """
    AMD text classifier with graceful fallback.

    Priority:
      1. Trained sklearn model (TF-IDF + LogReg) from joblib file
      2. Rule-based heuristic using VM_PHRASES and HUMAN_GREETINGS
    """

    def __init__(self, model_path: str | None = None):
        self.pipeline = None
        self.ready = False
        self._load_model(model_path)

    def _load_model(self, model_path: str | None):
        """Attempt to load a trained sklearn pipeline from joblib."""
        if model_path and Path(model_path).exists():
            try:
                import joblib
                self.pipeline = joblib.load(model_path)
                self.ready = True
                logger.info(f"Loaded trained AMD classifier from {model_path}")
                return
            except Exception as e:
                logger.warning(f"Failed to load classifier from {model_path}: {e}")

        # No trained model available — use rule-based fallback
        logger.info(
            "No trained classifier found — using rule-based fallback. "
            "Train a model with real campaign data for better accuracy."
        )
        self.ready = True

    def predict(self, transcript: str) -> dict:
        """
        Classify a transcript as human or machine.

        Returns:
            {
                "label": "human" | "machine",
                "confidence": float (0.0 - 1.0),
                "proba_human": float (0.0 - 1.0),
            }
        """
        if not transcript or not transcript.strip():
            return {
                "label": "unknown",
                "confidence": 0.0,
                "proba_human": 0.5,
            }

        text = transcript.strip().lower()

        # If we have a trained sklearn pipeline, use it
        if self.pipeline is not None:
            return self._predict_sklearn(text)

        # Otherwise, rule-based fallback
        return self._predict_rules(text)

    def _predict_sklearn(self, text: str) -> dict:
        """Predict using the trained TF-IDF + LogReg pipeline."""
        try:
            proba = self.pipeline.predict_proba([text])[0]
            classes = list(self.pipeline.classes_)

            # Get probability for each class
            human_idx = classes.index("human") if "human" in classes else 0
            machine_idx = classes.index("machine") if "machine" in classes else 1

            proba_human = float(proba[human_idx])
            proba_machine = float(proba[machine_idx])

            if proba_human >= proba_machine:
                label = "human"
                confidence = proba_human
            else:
                label = "machine"
                confidence = proba_machine

            return {
                "label": label,
                "confidence": round(confidence, 4),
                "proba_human": round(proba_human, 4),
            }
        except Exception as e:
            logger.error(f"sklearn prediction failed: {e}")
            return self._predict_rules(text)

    def _predict_rules(self, text: str) -> dict:
        """
        Rule-based fallback classifier.

        Strategy:
          1. If transcript matches a short human greeting exactly → HUMAN (high conf)
          2. If transcript contains VM indicator phrases → MACHINE (scaled by match count)
          3. If transcript is very short (1-3 words) with no VM phrases → HUMAN (medium conf)
          4. If transcript is long (>8 words) → lean MACHINE
          5. Otherwise → uncertain
        """
        words = text.split()
        word_count = len(words)

        # Check for exact short human greeting match
        if text.rstrip("?!.,") in HUMAN_GREETINGS or text in HUMAN_GREETINGS:
            return {
                "label": "human",
                "confidence": 0.90,
                "proba_human": 0.90,
            }

        # Count VM phrase matches
        vm_matches = sum(1 for phrase in VM_PHRASES if phrase in text)

        if vm_matches >= 2:
            # Multiple VM phrases = high confidence machine
            confidence = min(0.95, 0.80 + vm_matches * 0.05)
            return {
                "label": "machine",
                "confidence": round(confidence, 4),
                "proba_human": round(1.0 - confidence, 4),
            }
        elif vm_matches == 1:
            # Single VM phrase = moderate confidence machine
            return {
                "label": "machine",
                "confidence": 0.75,
                "proba_human": 0.25,
            }

        # Short transcript with no VM phrases → likely human
        if word_count <= 3:
            return {
                "label": "human",
                "confidence": 0.75,
                "proba_human": 0.75,
            }

        # Long transcript with no VM phrases → lean machine (could be IVR menu)
        if word_count > 8:
            return {
                "label": "machine",
                "confidence": 0.65,
                "proba_human": 0.35,
            }

        # Medium length, no clear signal → uncertain
        return {
            "label": "human",
            "confidence": 0.55,
            "proba_human": 0.55,
        }
