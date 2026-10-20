# Retained Termux preparation inputs

This directory preserves twelve exact original APT archives needed by the unpublished next-stable compatibility work. Their original Termux pool URLs returned HTTP 404 on 20 October 2026 after the rolling repository changed. Keeping these bytes makes the frozen preparation inputs available without selecting newer dependencies or changing the released Hermes package.

In the initial seven-archive recovery, the original Python archive was recovered from two earlier Actions artifacts. The other six archives were recovered from HTTPS mirrors listed by the official Termux mirror wiki: repository.su for abseil-cpp, fmt and libwebp; mirror.nyist.edu.cn for libprotobuf, python-torch and python-torchcodec. HTTP availability alone was not admission: each retained body matches the exact size and SHA-256 in the original frozen Packages index, and its original control fields match the pinned Package, Version and Architecture.

| Package | Version | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| abseil-cpp | 20260526.0 | 1,197,740 | e489fac652cddc39d9436141e627285f1034a545a06fbb19c420514a419ad877 |
| fmt | 1:11.2.0-1 | 168,824 | dad595afcb3b1096d725c6772c0c5531764caa5841affba3c533c6298a32ab08 |
| libprotobuf | 2:36.2 | 1,434,244 | 2f79e70af72127b6e9d8e8ea1a8bf261ea5f390914e667049b4f1dbc81f21fb0 |
| libwebp | 1.6.0-rc1-0 | 329,496 | 80fa46bec4faad0ccfd969df5acfd501d813ca9d112b5c49f3f91390e987f3a9 |
| python | 3.14.6-1 | 4,816,756 | 3166e56c2b6c03fff41191fbb9d736302978e7c484702814d9f6dc99dd6006bd |
| python-torch | 2.14.1-2 | 36,675,500 | cb5d96877f30bca10a0a19bcd32934a4f477ec7e5bfd00c2a82ac5c9e7d0eb73 |
| python-torchcodec | 0.17.0-1 | 571,432 | 743240ce85592ed31f05e95e139490c5a94c3bc8fe3c519b32d52e1585a5117f |

The [Python provenance receipt](python-3.14.6-1-provenance.json) records the earlier artifact identities and index binding. The [mirror recovery receipt](mirror-recovery-provenance.json) records the six retrieval URLs, original index identities, archive control fields, and original license/copyright members. All archive bytes are unchanged; no member, metadata, copyright notice or license was rewritten or removed. Windows-safe filenames encode a version epoch colon as %3A; this changes only the cache filename, never the archive or its signed package version.

## Additional APT-extension inputs

The first native retry at source d215961 passed preparation of the 122 foundation archives, then found removed Pillow/PyArrow archive URLs before Docker started. A scan of the APT-extension, non-Rust and Rust provenance closures found five additional unavailable original inputs. Pillow and PyArrow were recovered from two matching existing caches; apache-orc, libarrow-cpp and libre2 came from the previously listed HTTPS mirrors. All five preserve their signed index identities, original control fields and license members. The [extension recovery receipt](apt-extension-recovery-provenance.json) records their exact sources and verification.

| Package | Version | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| apache-orc | 2.3.1-1 | 406,700 | 246d1e51beed58bb63ac493f9bdd0dc0c0c19d51464af3e907d93d2de49893f8 |
| libarrow-cpp | 26.0.0-2 | 6,752,236 | 002ede93f64abe7ee49cf0c9fff4f411eb89e76e2aa5d11b5fb768d1115f4bb4 |
| libre2 | 2025-11-05-2 | 166,132 | 344be7b78860c541b312c452c2f3265adf965400e0cdc1ab780b8d50085b1fa3 |
| python-pillow | 12.3.0 | 407,220 | 3add75907c16921a32d2c6053a69086b25adcdf746269a0d2c62e712443e3073 |
| python-pyarrow | 26.0.0-2 | 3,444,216 | d9cc369295b3e6eabd93a835cdc963bb1c37631136b6d9d665dd3cba9855b531 |

Preparation consumers must verify the original pinned archive size and SHA-256 before copying or installing it. The shared foundation preparer and Rust source preparer use this directory through their existing --cache input. Native APT installation must still authenticate the frozen index with the original Termux signing key and enforce its exact package plan. The cache does not authorize a version substitution, dependency change, relaxed signature check, or release promotion.
