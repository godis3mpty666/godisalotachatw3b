try:
    from shared.build_provenance import BUILD_SUFFIX
except ImportError:
    BUILD_SUFFIX = ""

APP_VERSION = "1.20" + BUILD_SUFFIX
