try:
    from shared.build_provenance import BUILD_SUFFIX
except ImportError:
    BUILD_SUFFIX = ""

APP_VERSION = "0.77" + BUILD_SUFFIX
