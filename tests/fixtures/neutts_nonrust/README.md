# Exact SentencePiece source fixture

`sentencepiece_build_bundled.sh` is the unchanged `build_bundled.sh` from the public SentencePiece 0.2.2 source distribution, licensed under Apache-2.0 by its upstream authors. It is retained solely to replay the portable compiler-flag and bounded-job repair independently with Git and argument-recording shell functions.

The source archive is 8,218,435 bytes, SHA256 `3d2b5e824b5622038dc7b490897efe05ebbbb9e7350fc142f3ecc8789ef9bdf6`. This fixture is 797 bytes, SHA256 `9e220e130f5bec5b50dd7ddf5a6008300b7b6617e6b5d9261758abbe4210b6c5`. The full source inventory, archive URL and complete license remain in the exact preparation source input and `scripts/neutts_nonrust_runtime_lock.json`.

Host tests record CMake arguments; they do not compile SentencePiece or claim Android compatibility.
