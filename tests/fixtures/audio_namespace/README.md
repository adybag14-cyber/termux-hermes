# Original Termux audio wrapper fixture

This is the exact public libandroid-stub_30-2_aarch64.deb used by the audio
preparer, retained as a small integrity fixture. SHA-256:
74087792a86e3f90772627f2217797e422e5d5fc47f24ad825fc3bbb539a667a
(26,788 bytes).

Source: https://packages.termux.dev/apt/termux-main/pool/main/liba/libandroid-stub/libandroid-stub_30-2_aarch64.deb

Tests read the original archive's two relevant members and exercise the owned
copy/validation boundary without loading any native library on the host. The
OpenSL ES wrapper needs libtermux-platform-ns.so; that namespace library needs
only libc.so and libdl.so. Their original archive and ELF evidence is retained
in the audio namespace audit. No third-party files are modified.
