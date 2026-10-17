from .da8w4_concat_linear_fusion_cpu import register_da8w4_concat_linear_cpu_pass


def __getattr__(name):
    if name == "_int8_sdpa_init":
        # Import compiler-specific SDPA code only when the pass is requested.
        from .int8_sdpa_fusion import _int8_sdpa_init

        globals()[name] = _int8_sdpa_init
        return _int8_sdpa_init
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "_int8_sdpa_init",
    "register_da8w4_concat_linear_cpu_pass",
]
