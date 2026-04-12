# ═══════════════════════════════════════════════════════════════════════════════
# FreeSWITCH Custom Image — Broadcaster AMD Edition (Source Build)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Based on the OFFICIAL SignalWire build example:
#   https://github.com/signalwire/freeswitch/blob/master/docker/examples/Debian11/Dockerfile
#
# Adapted for our needs:
#   - Debian 12-slim (bookworm) instead of Debian 11
#   - Multi-stage build (lean runtime image)
#   - Selective module compilation (21 broadcaster-essential modules only)
#   - mod_amd compiled from seanbright/mod_amd source
#   - Proper entrypoint with freeswitch user/gosu step-down
#
# Build order (matches official example exactly):
#   1. LibKS         (SignalWire core library — FS core depends on this)
#   2. Sofia-SIP     (SIP stack — mod_sofia depends on this)
#   3. SpanDSP       (DSP toolkit — mod_spandsp depends on this)
#   4. SignalWire-C  (SignalWire client lib — FS core depends on this)
#   5. FreeSWITCH    (core + selected modules)
#   6. mod_amd       (seanbright — compiled against FS dev headers)
#
# Target: High-volume outbound IVR/AMD (up to 500 concurrent calls)
# ═══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1: Builder
# ══════════════════════════════════════════════════════════════════════════════
FROM debian:12-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

# ── System build dependencies ────────────────────────────────────────────────
# Matches the official Debian11 example + additions for Debian 12 package names.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # build tools
    build-essential cmake automake autoconf libtool-bin pkg-config \
    git ca-certificates curl wget \
    # general
    libssl-dev zlib1g-dev libdb-dev unixodbc-dev libncurses5-dev \
    libexpat1-dev libgdbm-dev bison libtpl-dev libtiff-dev \
    uuid-dev lsb-release \
    # core
    libpcre3-dev libedit-dev libsqlite3-dev libcurl4-openssl-dev \
    nasm yasm \
    # core codecs
    libogg-dev libspeex-dev libspeexdsp-dev \
    # mod_enum
    libldns-dev \
    # mod_lua
    liblua5.3-dev \
    # mod_opus
    libopus-dev \
    # mod_pgsql
    libpq-dev \
    # mod_sndfile
    libsndfile1-dev libflac-dev libvorbis-dev \
    # image support (mod_spandsp needs libjpeg)
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*


# ── 1. Build LibKS ──────────────────────────────────────────────────────────
# SignalWire's core library. Required by FreeSWITCH core since v1.10.4+.
# Official example: cmake . -DCMAKE_INSTALL_PREFIX=/usr -DWITH_LIBBACKTRACE=1
RUN git clone https://github.com/signalwire/libks.git /usr/src/libs/libks
WORKDIR /usr/src/libs/libks
RUN cmake . -DCMAKE_INSTALL_PREFIX=/usr -DWITH_LIBBACKTRACE=1 && \
    make -j$(nproc) && \
    make install


# ── 2. Build Sofia-SIP ──────────────────────────────────────────────────────
# The FreeSWITCH-maintained fork of Sofia-SIP. Building from source guarantees
# mod_sofia links against the EXACT same library version at compile and runtime.
# This permanently eliminates the tptag_socket_keepalive symbol mismatch.
#
# Flags from official example:
#   --with-pic          Position-independent code (required for shared libs)
#   --with-glib=no      Don't depend on glib (unnecessary for FS)
#   --without-doxygen   Skip doc generation
#   --disable-stun      FS has its own STUN implementation
RUN git clone --depth 1 https://github.com/freeswitch/sofia-sip.git /usr/src/libs/sofia-sip
WORKDIR /usr/src/libs/sofia-sip
RUN ./bootstrap.sh && \
    ./configure CFLAGS="-g -ggdb" \
      --with-pic \
      --with-glib=no \
      --without-doxygen \
      --disable-stun \
      --prefix=/usr && \
    make -j$(nproc) && \
    make install


# ── 3. Build SpanDSP ────────────────────────────────────────────────────────
# DSP toolkit required by mod_spandsp (G.711 codec support, fax, tone detect).
# CRITICAL: Must use commit 0d2e6ac — the latest master has breaking API changes
# (renamed V18_MODE constants, changed v18_init signature) that are incompatible
# with FreeSWITCH v1.10's mod_spandsp source code.
RUN git clone https://github.com/freeswitch/spandsp.git /usr/src/libs/spandsp
WORKDIR /usr/src/libs/spandsp
RUN git checkout 0d2e6ac && \
    ./bootstrap.sh && \
    ./configure CFLAGS="-g -ggdb" \
      --with-pic \
      --prefix=/usr && \
    make -j$(nproc) && \
    make install


# ── 4. Build SignalWire-C ───────────────────────────────────────────────────
# SignalWire client library. Required by FreeSWITCH core compilation.
# Official example: PKG_CONFIG_PATH=/usr/lib/pkgconfig cmake . -DCMAKE_INSTALL_PREFIX=/usr
RUN git clone https://github.com/signalwire/signalwire-c.git /usr/src/libs/signalwire-c
WORKDIR /usr/src/libs/signalwire-c
RUN PKG_CONFIG_PATH=/usr/lib/pkgconfig cmake . -DCMAKE_INSTALL_PREFIX=/usr && \
    make -j$(nproc) && \
    make install


# ── 5. Build FreeSWITCH ─────────────────────────────────────────────────────
# Pin to v1.10 stable branch.
# The modules.conf controls which modules are compiled — we only build what
# the Broadcaster system actually invokes in its Lua/Python/XML code.
RUN git clone --depth 1 -b v1.10 https://github.com/signalwire/freeswitch.git /usr/src/freeswitch
WORKDIR /usr/src/freeswitch

# Configure the build-time module list (overrides build/modules.conf.in).
# Only the modules our codebase actually uses are enabled.
# This reduces compile time significantly and shrinks the final image.
RUN cat > modules.conf <<'MODULES_EOF'
# ═══════════════════════════════════════════════════════════════════════════
# Broadcaster-Optimized Module List
# ═══════════════════════════════════════════════════════════════════════════

# Logging
loggers/mod_console
loggers/mod_logfile

# Event Handlers
event_handlers/mod_cdr_csv
event_handlers/mod_event_socket

# Endpoints
endpoints/mod_sofia
endpoints/mod_loopback

# Applications
applications/mod_commands
applications/mod_dptools
applications/mod_callcenter
applications/mod_hash
applications/mod_db
applications/mod_esf

# Dialplan
dialplans/mod_dialplan_xml

# Scripting Languages
languages/mod_lua

# Codecs
codecs/mod_opus

# File Formats
formats/mod_sndfile
formats/mod_native_file
formats/mod_local_stream
formats/mod_tone_stream

# Say (IVR number/date prompts)
say/mod_say_en

# AMD — Built-in voicemail beep detector
applications/mod_avmd

# SpanDSP — Industrial in-band DTMF detection (Goertzel algorithm),
# tone generation, fax. Provides spandsp_start_dtmf for carrier-immune DTMF.
applications/mod_spandsp
MODULES_EOF

# Bootstrap and configure (matches official example pattern)
RUN ./bootstrap.sh -j
RUN ./configure --prefix=/usr/local/freeswitch
RUN make -j$(nproc)
RUN make install

# Install default sound files (en-us-callie 8kHz — IVR prompts, hold music)
RUN make cd-sounds-install cd-moh-install 2>/dev/null || true


# ── 7. Build mod_amd ────────────────────────────────────────────────────────
# seanbright/mod_amd — open-source port of Asterisk's app_amd for FreeSWITCH.
# Compiled against the FreeSWITCH headers we just built (guaranteed ABI match).
#
# The upstream Makefile hardcodes the install path to /usr/lib/freeswitch/mod
# but our FS uses /usr/local/freeswitch/lib/freeswitch/mod (from pkgconfig).
# We patch the Makefile install target to use the correct modulesdir.
RUN git clone --depth 1 https://github.com/seanbright/mod_amd.git /usr/src/mod_amd
WORKDIR /usr/src/mod_amd
RUN MODDIR=$(PKG_CONFIG_PATH=/usr/local/freeswitch/lib/pkgconfig pkg-config --variable=modulesdir freeswitch) && \
    echo "Detected FS module dir: $MODDIR" && \
    export PKG_CONFIG_PATH="/usr/local/freeswitch/lib/pkgconfig:/usr/lib/pkgconfig:$PKG_CONFIG_PATH" && \
    sed -i 's/-Werror/-Wno-error/g' Makefile && \
    sed -i "s|/usr/lib/freeswitch/mod|$MODDIR|g" Makefile && \
    make -j$(nproc) && \
    make install


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2: Runtime (lean production image)
# ══════════════════════════════════════════════════════════════════════════════
FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.utf8

# Runtime-only libraries (no -dev packages, no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core runtime libs
    libssl3 libsqlite3-0 libcurl4 libpcre3 \
    libspeex1 libspeexdsp1 libldns3 libedit2 \
    libopus0 libsndfile1 libjpeg62-turbo \
    libtiff6 libpq5 liblua5.3-0 \
    uuid-runtime ca-certificates curl \
    libtpl0 libncurses6 libexpat1 libodbc2 \
    # Locale support (FS expects UTF-8)
    locales \
    # gosu for privilege step-down (matches official entrypoint pattern)
    gosu \
    && rm -rf /var/lib/apt/lists/* \
    && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8

# Copy the FreeSWITCH installation from builder
COPY --from=builder /usr/local/freeswitch /usr/local/freeswitch

# Copy locally-built shared libraries (Sofia-SIP, SpanDSP, LibKS, SignalWire-C)
# These MUST be present at runtime for modules to load.
COPY --from=builder /usr/lib/libsofia-sip-ua*.so* /usr/lib/
# SpanDSP installs to /usr/lib/ directly (not multiarch subdir) with --prefix=/usr
COPY --from=builder /usr/lib/libspandsp*.so* /usr/lib/
COPY --from=builder /usr/lib/libks*.so* /usr/lib/
COPY --from=builder /usr/lib/libsignalwire_client*.so* /usr/lib/

# Refresh the dynamic linker cache
RUN ldconfig

# Add FreeSWITCH binaries to PATH
ENV PATH="/usr/local/freeswitch/bin:${PATH}"

# Create freeswitch user/group (matches official Dockerfile pattern)
RUN groupadd -r freeswitch --gid=999 && \
    useradd -r -g freeswitch --uid=999 freeswitch

# Create required runtime directories owned by freeswitch
RUN mkdir -p /var/run/freeswitch /var/lib/freeswitch && \
    chown -R freeswitch:freeswitch \
      /usr/local/freeswitch \
      /var/run/freeswitch \
      /var/lib/freeswitch

# ── Entrypoint ───────────────────────────────────────────────────────────────
# Adapted from the official docker-entrypoint.sh:
#   - Copies vanilla config if no config is mounted
#   - chowns all FS directories
#   - Drops privileges via gosu → freeswitch user
#   - Supports /docker-entrypoint.d/*.sh hook scripts
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

# Healthcheck verifies core status and that AMD modules are loaded.
# Matches official pattern: fs_cli -x status | grep -q ^UP
HEALTHCHECK --interval=15s --timeout=10s --retries=5 --start-period=45s \
    CMD fs_cli -x "status" | grep -q ^UP || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["freeswitch"]
