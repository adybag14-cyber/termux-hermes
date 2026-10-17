from pkg_resources import resource_filename
PREPACKAGED_MODELS_DIR = resource_filename(__name__, "pretrained")

from .perth_net_implicit.perth_watermarker import PerthImplicitWatermarker
