try:
    from shared.build_provenance import BUILD_SUFFIX
except ImportError:
    BUILD_SUFFIX = ""

APP_VERSION = "2.00" + BUILD_SUFFIX
