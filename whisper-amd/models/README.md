# Placeholder — no pre-trained model shipped.
# The classifier falls back to rule-based heuristics.
# See classifier.py for details.
# 
# To train a custom model:
#   1. Collect transcripts: CSV with columns: text,label (human|machine)
#   2. python scripts/train_text_classifier.py --csv data.csv --out models/text_cls.joblib
#   3. Restart the whisper-amd service
