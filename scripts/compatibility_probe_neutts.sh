#!/usr/bin/env bash
# Separate APT-only native ABI experiment. Does not install NeuTTS or modify Hermes.
set -Eeuo pipefail

mode=host
if [[ "${1:-}" == --in-container ]]; then mode=container; shift; fi
[[ $# == 2 && "$1" == --out ]] || { echo "usage: $0 [--in-container] --out NEW_DIR" >&2; exit 2; }
out="$2"

if [[ "$mode" == host ]]; then
  case "$(uname -m)" in aarch64|arm64) ;; *) echo "Native ARM64 host required" >&2; exit 2 ;; esac
  packaging="$(cd "$(dirname "$0")/.." && pwd)"
  [[ ! -e "$out" ]] || { echo "Use a new evidence directory" >&2; exit 2; }
  mkdir -p "$out"
  out="$(realpath "$out")"
  image='termux/termux-docker@sha256:c14ffb703abf44f2d3bf7fdffdcc50df7d1454d09c705be190e0342a0b47f303'
  python3 - "$packaging" "$out" "$image" <<'PY'
import hashlib, json, os, pathlib, subprocess, sys
root, out = map(pathlib.Path, sys.argv[1:3])
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
if os.environ.get("NEUTTS_PROBE_HEAD_SHA", head) != head:
    raise SystemExit("advertised head differs from the actual checkout")
if json.loads((root / "manifest/release.json").read_text())["termux_image"] != sys.argv[3]:
    raise SystemExit("review the native image pin before changing this experiment")
names = ("scripts/compatibility_probe_neutts.sh", ".github/workflows/neutts-termux-probe.yml")
data = {
    "schema_version": 1, "purpose": "unpublished APT-only NeuTTS dependency feasibility",
    "run_id": os.environ.get("GITHUB_RUN_ID"), "head_sha": head,
    "workflow_ref_commit": os.environ.get("GITHUB_SHA"), "native_image": sys.argv[3],
    "inputs": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in names},
    "recipe_repository": "termux/termux-packages",
    "reviewed_recipe_commit": "ae877f2c6a2b2318abeb43699d6ec5f619c216a6",
    "reviewed_index_url": "https://packages.termux.dev/apt/termux-main/dists/stable/main/binary-aarch64/Packages.gz",
    "reviewed_index_sha256": "0f9ea9b4cd6c0f7c3ffe90bea8afb7e25a61adc319fc90eca3d0979da6dcb923",
    "declared_engine_commit": "b7a3427d0d25e20e8b9e92cbaae688f732916baf",
    "engine_installed": False, "synthesis_tested": False, "physical_device_tested": False,
    "hermes_candidate_installed": False, "pm_admission_changed": False, "release_output": False,
}
(out / "NEUTTS-PROBE-INPUTS.json").write_text(json.dumps(data, indent=2) + "\n")
PY
  chmod 0777 "$out"
  docker pull "$image"
  [[ "$(docker image inspect "$image" --format '{{.Architecture}}')" == arm64 ]]
  container="hermes-neutts-${GITHUB_RUN_ID:-local}-$$"
  finish_host() { docker rm -f "$container" >/dev/null 2>&1 || true; }
  trap finish_host EXIT
  timeout --signal=TERM --kill-after=20s 24m docker run --rm --name "$container" \
    --platform linux/arm64 --user 1000:1000 --cpus 2 --memory 8g --pids-limit 512 \
    --tmpfs /bin:mode=1777 \
    -v "$packaging:/probes:ro" -v "$out:/out" \
    "$image" bash /probes/scripts/compatibility_probe_neutts.sh --in-container --out /out \
    2>&1 | tee "$out/neutts-native-probe.log"
  exit 0
fi

[[ "$(id -u)" == 1000 ]] || { echo "The native probe must run as UID1000" >&2; exit 2; }
export PREFIX=/data/data/com.termux/files/usr
export TMPDIR="$PREFIX/tmp"
export PATH="$PREFIX/bin:/system/bin:/system/xbin"
export DEBIAN_FRONTEND=noninteractive TERMUX_PKG_NO_MIRROR_SELECT=1
export PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
unset LD_LIBRARY_PATH LD_PRELOAD PYTHONPATH PYTHONHOME HERMES_RUNTIME_DIR HERMES_HOME
umask 077
mkdir -p "$TMPDIR"
work="$(mktemp -d "$TMPDIR/neutts-core.XXXXXX")"
stage=setup
finish() {
  status=$?
  trap - EXIT
  printf '{"schema_version":1,"stage":"%s","exit_code":%s}\n' "$stage" "$status" > "$out/NEUTTS-EXIT.json"
  find "$out" -xdev -uid "$(id -u)" -type f -exec chmod a+r {} +
  find "$out" -xdev -uid "$(id -u)" -type d -exec chmod a+rx {} +
  rm -rf -- "$work"
  exit "$status"
}
trap finish EXIT

# Exact declared dependency closure for the eight scientific packages. The only
# alternative dependency is vulkan-icd, fixed here to Mesa's CPU software driver.
# Columns: Package, Version, Architecture, SHA256, Size, official archive path.
cat > "$work/PINNED-APT.tsv" <<'PINS'
abseil-cpp	20260526.0	aarch64	e489fac652cddc39d9436141e627285f1034a545a06fbb19c420514a419ad877	1197740	pool/main/a/abseil-cpp/abseil-cpp_20260526.0_aarch64.deb
brotli	1.2.0	aarch64	db1502601d40fb44e6085ad8bfd9311a8b472e98db831ceec9d404c5708bb52c	340592	pool/main/b/brotli/brotli_1.2.0_aarch64.deb
ca-certificates	1:2026.09.25	all	57fab24bf4561bfdd35afe71bc1929914e51c35458cfd1fca2b15e54bc8df7af	105404	pool/main/c/ca-certificates/ca-certificates_1:2026.09.25_all.deb
ffmpeg	9.0.2	aarch64	3cdde6ab05ad6fab1cbee7addce41e2eeaa4a1e5bcb753f17632e67077edc5b8	11558068	pool/main/f/ffmpeg/ffmpeg_9.0.2_aarch64.deb
fftw	3.3.11	aarch64	0a5140986bbfc69dbfa8f939f78521fb3dc02a193b6c822b7218dae44d99ffd5	1004996	pool/main/f/fftw/fftw_3.3.11_aarch64.deb
fmt	1:11.2.0-1	aarch64	dad595afcb3b1096d725c6772c0c5531764caa5841affba3c533c6298a32ab08	168824	pool/main/f/fmt/fmt_1:11.2.0-1_aarch64.deb
fontconfig	2.18.3	aarch64	7f8b70dd7ca85b1e7cbb14a11e9e6bd4ce3189ab985aa7af51145484d85f2c61	140288	pool/main/f/fontconfig/fontconfig_2.18.3_aarch64.deb
freetype	2.15.0	aarch64	fe217807b22aa40029874eb1d9e01b89a01b5f1e4f0556c4de9c8e83c4db4256	422056	pool/main/f/freetype/freetype_2.15.0_aarch64.deb
fribidi	1.0.17	aarch64	879a180b10e105600fb6033f15eff0987eb48ae11f1b87beeca803aab84b8666	66848	pool/main/f/fribidi/fribidi_1.0.17_aarch64.deb
game-music-emu	0.6.5	aarch64	ffe1c43919d485409b2459d462b2dc6389492afeea869aef701b391a4ed29c67	127952	pool/main/g/game-music-emu/game-music-emu_0.6.5_aarch64.deb
gdbm	1.26-1	aarch64	c378de833aae3cf41f3028491ea11836479d9833ab653edc27d0c0e0e691d5c5	150284	pool/main/g/gdbm/gdbm_1.26-1_aarch64.deb
gdk-pixbuf	2.44.8	aarch64	213da5186fc4ccca336ee7debf150c01c8de72ecb9575950d58f55e535267795	153228	pool/main/g/gdk-pixbuf/gdk-pixbuf_2.44.8_aarch64.deb
gflags	2.3.1	aarch64	042b07cab88d3b8cac24fb57a34eeb6bfceb303180bf6f22dd564ee2cf132adb	79672	pool/main/g/gflags/gflags_2.3.1_aarch64.deb
giflib	6.1.3	aarch64	c46823a7a9cb07f1f833392e36d0ead162f9972a4d3881a6e4b5700ec55b2534	43832	pool/main/g/giflib/giflib_6.1.3_aarch64.deb
glib	2.90.1	aarch64	132d8ce961d96a7252fd4bc2228bddd385b1b17b706a46caae6d541ae0e4b2c0	2573108	pool/main/g/glib/glib_2.90.1_aarch64.deb
glslang	16.6.0	aarch64	c5b5d6cb57d5841966c4b07033d319ebf6a3df61347a484b9dc5e332d29cd721	2543452	pool/main/g/glslang/glslang_16.6.0_aarch64.deb
google-glog	0.7.1-2	aarch64	de16afa5579cd9ea3f942407890e5dbbce3b7321c497c624e4b26f98c5f8de50	103736	pool/main/g/google-glog/google-glog_0.7.1-2_aarch64.deb
harfbuzz	14.6.0	aarch64	eeeebc3cb1d10612ef5e53c1ecdf1b15f36889592e847d10774f350ba07ecf74	884052	pool/main/h/harfbuzz/harfbuzz_14.6.0_aarch64.deb
highway	1.4.0-1	aarch64	71b8e0c231ab6b66827374543d55997a5cb02d8882f5d53e059ba78cd2511da1	682536	pool/main/h/highway/highway_1.4.0-1_aarch64.deb
libandroid-complex-math	0.2	aarch64	32786717f21af152deff76b34aa3a5c94507f28d46e2ef92dcfae70021f14f48	9572	pool/main/liba/libandroid-complex-math/libandroid-complex-math_0.2_aarch64.deb
libandroid-execinfo	0.1-3	aarch64	725dd2c6da7fc96e860fcc928e18aa9fb0e85e0bdcaf4f8ce0f0654ca6860fc2	14964	pool/main/liba/libandroid-execinfo/libandroid-execinfo_0.1-3_aarch64.deb
libandroid-glob	0.6-3	aarch64	2276ae8adedf0db76c2f4ffc94cc4cceb2f4f5d78e021b54e2e046d1233e7826	7032	pool/main/liba/libandroid-glob/libandroid-glob_0.6-3_aarch64.deb
libandroid-posix-semaphore	0.1-4	aarch64	0efa8677a0166315ba4e685863712eba0ca0a1732827492f38226e2723730c7a	4076	pool/main/liba/libandroid-posix-semaphore/libandroid-posix-semaphore_0.1-4_aarch64.deb
libandroid-shmem	0.7	aarch64	0da3a24d558b93c92bcf8d611e0826a99ff96e396b148e6cdf33b47c47c57ff6	7216	pool/main/liba/libandroid-shmem/libandroid-shmem_0.7_aarch64.deb
libandroid-stub	30-2	aarch64	74087792a86e3f90772627f2217797e422e5d5fc47f24ad825fc3bbb539a667a	26788	pool/main/liba/libandroid-stub/libandroid-stub_30-2_aarch64.deb
libandroid-support	29-1	aarch64	f2f145d6135ad4843ac9670153be3e3944dc1e6f1736d46d2306c28f2b86f517	10880	pool/main/liba/libandroid-support/libandroid-support_29-1_aarch64.deb
libaom	3.15.2	aarch64	13649d69b98ca21dcf74193da9ef033aced13820bba58fde742b0bd4de44c282	2081824	pool/main/liba/libaom/libaom_3.15.2_aarch64.deb
libass	0.17.5	aarch64	4f94205285ea2062be4f60e695723a6f3350339ec89720943b0dce5ae30db01d	85252	pool/main/liba/libass/libass_0.17.5_aarch64.deb
libavif	1.4.2	aarch64	98d2b89c5547d07191c55c7a4efe4a0906c600953b62504056ebe96baafce52e	385324	pool/main/liba/libavif/libavif_1.4.2_aarch64.deb
libbluray	1.5.1	aarch64	fbe931e6a7d9604fe865bd24b8012ad3b7f04c6bbb6cf9b277760db1b4a8df7e	110932	pool/main/libb/libbluray/libbluray_1.5.1_aarch64.deb
libbs2b	3.1.0-2	aarch64	c71660d99e4baa064ba93f0ef750b6b2ea0d1d494a754cf1c67b550bb4baa91d	13636	pool/main/libb/libbs2b/libbs2b_3.1.0-2_aarch64.deb
libbz2	1.0.8-8	aarch64	4335d7f060650b0aabef545d1334c2f9f280223d5962e13c24a00ec934b794ba	26116	pool/main/libb/libbz2/libbz2_1.0.8-8_aarch64.deb
libc++	30	aarch64	53d0b84a7ba7459024257cb94d5b136fe13ef858567f65a8064b35950799f2ca	341604	pool/main/libc/libc++/libc++_30_aarch64.deb
libcairo	1.18.6	aarch64	c2caebbd7a5e2c778729868fdbae54f87a324cccb5ad254bcae050a412d9cd57	487700	pool/main/libc/libcairo/libcairo_1.18.6_aarch64.deb
libcrypt	0.2-6	aarch64	6c283eed576b98cc3568f99638156f8588f77d979579d03bef8683d6eb8601e1	8880	pool/main/libc/libcrypt/libcrypt_0.2-6_aarch64.deb
libdav1d	1.5.4	aarch64	4c2ffdcbbb805727caaa2e91b56917830dbacf4245dd439cf2e1c0d61a541613	265960	pool/main/libd/libdav1d/libdav1d_1.5.4_aarch64.deb
libde265	1.1.3	aarch64	3c38af85b13a638b377fab1b7389aae2aca5067e21db29c058d5746f52ea7114	198836	pool/main/libd/libde265/libde265_1.1.3_aarch64.deb
libdrm	2.4.134	aarch64	0cbe82140cf325c15473fbf53a3711fc7a2fb88e36a3eea58a3267c461ab4a17	180604	pool/main/libd/libdrm/libdrm_2.4.134_aarch64.deb
libdvdnav	7.0.0	aarch64	fd8509a88b5966cdadf9925b2687e50c31d796e773cb326e651e76c0a3b16958	49404	pool/main/libd/libdvdnav/libdvdnav_7.0.0_aarch64.deb
libdvdread	7.1.1	aarch64	8e1606f7d2aec40c9e8f748ab595cf0f684c998b4642bc59fa6b18b5fe1d2fb0	78252	pool/main/libd/libdvdread/libdvdread_7.1.1_aarch64.deb
libexpat	2.9.0	aarch64	f8a104e8227c9c181f6818658a3ee2fa4c107fac94219b068144fc6591086cdb	100256	pool/main/libe/libexpat/libexpat_2.9.0_aarch64.deb
libffi	3.8.0	aarch64	4f255badf74cd31f6a2801c17fa1444199c84c834b517b7c843e2fe9ebe91d77	37592	pool/main/libf/libffi/libffi_3.8.0_aarch64.deb
libflac	1.5.0-1	aarch64	d1d6fcac6fd6d15c36f34464cb01d5e2140e321d8448dfc396cd7eb1536b1f6c	202828	pool/main/libf/libflac/libflac_1.5.0-1_aarch64.deb
libgraphite	1.3.15	aarch64	15ac85737a35150cecb9e46ecb32567ae2a4fc28071cdf58fb95e1b77d7889d9	82208	pool/main/libg/libgraphite/libgraphite_1.3.15_aarch64.deb
libheif	1.23.6	aarch64	14681f626daef5eac65bbfce8eadcc3add8fb881de3fafa2ea3014c6f8b46ffe	595916	pool/main/libh/libheif/libheif_1.23.6_aarch64.deb
libiconv	1.19	aarch64	fe9481b1dc101c6c3552943f25435109fd522aecc615ae49594f9fbee863bb37	562724	pool/main/libi/libiconv/libiconv_1.19_aarch64.deb
libjpeg-turbo	3.2.0	aarch64	e6339075bcde28b4902d5a51f4063164834abfd2fa115e881ae637a34585e54f	453600	pool/main/libj/libjpeg-turbo/libjpeg-turbo_3.2.0_aarch64.deb
libjxl	0.12.0-2	aarch64	cccbdcea369bb722915c97ed36550c7d304c11673f59e217089bdeabc59429b3	978528	pool/main/libj/libjxl/libjxl_0.12.0-2_aarch64.deb
libllvm	21.1.8-3	aarch64	5056a73f2645fc9c0759e6f94a1bd6edcf36305acaef58dc685211ced9cc2a02	30733892	pool/main/libl/libllvm/libllvm_21.1.8-3_aarch64.deb
liblzma	5.8.4	aarch64	44e95e6e60dddb3705e60a344a4f009a1085a210797342b721eaff41b44033c0	194796	pool/main/libl/liblzma/liblzma_5.8.4_aarch64.deb
liblzo	2.10-5	aarch64	b8a6d232d592dcd6529589c817927cca3254f3ab40a85fce873d997ace7d1ca2	69560	pool/main/libl/liblzo/liblzo_2.10-5_aarch64.deb
libmp3lame	4.0-1	aarch64	59f70ad8885578063bcbea3b11e74fb69e2416ca036b47aa255c1fa4f074565e	98588	pool/main/libm/libmp3lame/libmp3lame_4.0-1_aarch64.deb
libmpg123	1.33.7	aarch64	883b104faae53820b2e758363300ccf99e28f627a263d766af61ae07b73b07b3	175116	pool/main/libm/libmpg123/libmpg123_1.33.7_aarch64.deb
libmysofa	1.3.5	aarch64	b083050d4bc0bd11db0f73382ae3db8c5dc352520b78aaa44f150d87cff80215	1160956	pool/main/libm/libmysofa/libmysofa_1.3.5_aarch64.deb
libogg	1.3.6-1	aarch64	4f1700a532f251ad3600f44f88cd764f1f6b0542d3343391117944b47a92802d	188636	pool/main/libo/libogg/libogg_1.3.6-1_aarch64.deb
libopenblas	0.3.34	aarch64	c110b2925318d49e1d95adc13b6931ad57e08661427c5adca6ff0f2af35e8d27	2596208	pool/main/libo/libopenblas/libopenblas_0.3.34_aarch64.deb
libopencore-amr	0.1.6-1	aarch64	8ad25c12b892d56e85a21517d814146109fea7865b2548b8637743d7d6e0fee2	111688	pool/main/libo/libopencore-amr/libopencore-amr_0.1.6-1_aarch64.deb
libopenmpt	0.8.9	aarch64	80c0b91a3804edc69bd45ec8a9ef4f1d1a1b5be2b8712dafce9469069cc1acc0	543436	pool/main/libo/libopenmpt/libopenmpt_0.8.9_aarch64.deb
libopus	1.6.1	aarch64	005a9335ce0ec0f510bbe6e0229c901d6f920cc375fcda56461e96cef70f8ff0	191480	pool/main/libo/libopus/libopus_1.6.1_aarch64.deb
libpixman	0.46.4-1	aarch64	364b8c82ff68f8513930e5d413459fb7c52eccc7ba75a97a8c5a38760eee8d33	157712	pool/main/libp/libpixman/libpixman_0.46.4-1_aarch64.deb
libplacebo	7.360.1	aarch64	903ba38d4b1184a7fb37584e93967a73791f5df22fb3f81de5b33051b77b73ca	416772	pool/main/libp/libplacebo/libplacebo_7.360.1_aarch64.deb
libpng	1.6.59	aarch64	32d61f0b1a60cf7283aa3a80e288737493df2c6b84c8c749606b77c94a10f2b2	195892	pool/main/libp/libpng/libpng_1.6.59_aarch64.deb
libprotobuf	2:36.2	aarch64	2f79e70af72127b6e9d8e8ea1a8bf261ea5f390914e667049b4f1dbc81f21fb0	1434244	pool/main/libp/libprotobuf/libprotobuf_2:36.2_aarch64.deb
librav1e	0.8.1	aarch64	ac7842a5896bdff1b4d4974d9c02e60f7d4a587b8618df691118a8591f8dbccf	695340	pool/main/libr/librav1e/librav1e_0.8.1_aarch64.deb
libsamplerate	0.2.2-4	aarch64	521d46cc49557c00b2d5c107da1f86f0cdda8a3a3b84bd9958bd7fc52bec2dae	973440	pool/main/libs/libsamplerate/libsamplerate_0.2.2-4_aarch64.deb
libsndfile	1.2.2-3	aarch64	1e1fb77b14ec26f3ff6ded069e9ec816ab7535ae5d074122c6727b0f59d8aff3	223576	pool/main/libs/libsndfile/libsndfile_1.2.2-3_aarch64.deb
libsodium	1.0.22-1	aarch64	a9fbbc3a7a5a2a0f514474ee706d49b576ac09268b87142a3690edb9f5f3643d	150908	pool/main/libs/libsodium/libsodium_1.0.22-1_aarch64.deb
libsoxr	0.1.3-8	aarch64	a1c5f66aae3b9900e9a492b43901b2b98586870c7905feb9f3c835cc9af464be	282436	pool/main/libs/libsoxr/libsoxr_0.1.3-8_aarch64.deb
libsqlite	3.54.1	aarch64	0856cac8cc87f6e112f2eef4fcac6ad5cb08209ecb7cc260f997874fc186a3c0	768964	pool/main/libs/libsqlite/libsqlite_3.54.1_aarch64.deb
libsrt	1.5.7	aarch64	6199d01dd9d1630a32c220f7fdb9bca958adbd7062f90e9bfc010cf75fdef07a	279996	pool/main/libs/libsrt/libsrt_1.5.7_aarch64.deb
libssh	0.12.2	aarch64	05cfb1d6f70e9b316f1eac7a5ec9139f884e644d6d91e668e9ca49716aad8ff0	234304	pool/main/libs/libssh/libssh_0.12.2_aarch64.deb
libtheora	1.2.0-1	aarch64	9d4582f14f71df7a48101ee05297a57a898654ead55ef10ca4d73e254151b1e8	132020	pool/main/libt/libtheora/libtheora_1.2.0-1_aarch64.deb
libtiff	4.7.2	aarch64	998c583d65d7d42dcb177548a218545661f02385a51bb9f5c24f0da4fd046574	869912	pool/main/libt/libtiff/libtiff_4.7.2_aarch64.deb
libudfread	1.2.0	aarch64	61a7e02c30ae61f9cbe46bf8cefa8e361a16b29010a07cacb43513ff533df81c	15072	pool/main/libu/libudfread/libudfread_1.2.0_aarch64.deb
libv4l	1.32.0-1	aarch64	0b3102121ee91167a06de5e9b8b13524c76b7b8d6bdcf2ac57c18dc8e0254e6d	93336	pool/main/libv/libv4l/libv4l_1.32.0-1_aarch64.deb
libvidstab	1.1.2	aarch64	598d1c5ea7de4e4c76aa2198602e3dc35684671d9690e69d665058d55a89ab75	307236	pool/main/libv/libvidstab/libvidstab_1.1.2_aarch64.deb
libvmaf	3.2.1	aarch64	8c65e85997426c00ce6a419343eb820e164d725e4b267e268a9e8e351e2f9001	192520	pool/main/libv/libvmaf/libvmaf_3.2.1_aarch64.deb
libvo-amrwbenc	0.1.3-2	aarch64	aa913ca492246ed1e6ce57a3c52fe856c323cbb6e8dbdb6904b80214551f6e00	52344	pool/main/libv/libvo-amrwbenc/libvo-amrwbenc_0.1.3-2_aarch64.deb
libvorbis	1.3.7-4	aarch64	6bfd70c4b570b85594bd06116b75a6f8109ec58cbc123e938b630a6eefdedf4e	261740	pool/main/libv/libvorbis/libvorbis_1.3.7-4_aarch64.deb
libvpx	1:1.17.0	aarch64	1dbc5be0610c9da58732f480c7a27dbb32cf72a472e88c6c0993bdc0feeae00a	869952	pool/main/libv/libvpx/libvpx_1:1.17.0_aarch64.deb
libwayland	1.26.0	aarch64	f03ea02f7d523399514e2463c5459dab234b802bbda41a61c0340b4011dc773d	129444	pool/main/libw/libwayland/libwayland_1.26.0_aarch64.deb
libwebp	1.6.0-rc1-0	aarch64	80fa46bec4faad0ccfd969df5acfd501d813ca9d112b5c49f3f91390e987f3a9	329496	pool/main/libw/libwebp/libwebp_1.6.0-rc1-0_aarch64.deb
libx11	1.8.14	aarch64	c5206ee9cc26a63985d110b57bc24f23c7c97505e6100c4d6a8547a1aeed5532	1910512	pool/main/libx/libx11/libx11_1.8.14_aarch64.deb
libx264	1:0.164.3191-1	aarch64	fe98852cb06ce1c963a54284179d8cda42af2fa82afcac09f7d81e6de4d9bbc1	396540	pool/main/libx/libx264/libx264_1:0.164.3191-1_aarch64.deb
libx265	4.3	aarch64	8dbfd50ad2ceea5ffa2384f0f4cc16a87cbf56ac83b4861fa4f640d1beb352cd	1599320	pool/main/libx/libx265/libx265_4.3_aarch64.deb
libxau	1.0.12-2	aarch64	2d86bed61ce89dd8fdb55e565aede10155f2ce3adaccb61d5f1375aec3314083	9120	pool/main/libx/libxau/libxau_1.0.12-2_aarch64.deb
libxcb	1.17.0-1	aarch64	191c3642b6a8c754bc75b69b94a81858ecb5f18766dc085aff55559b8087ad34	913948	pool/main/libx/libxcb/libxcb_1.17.0-1_aarch64.deb
libxdmcp	1.1.5-2	aarch64	caea0cf5c0028af0840774094b8900ef7afffd8f9bbd7b1abfbe66851f0d6077	24460	pool/main/libx/libxdmcp/libxdmcp_1.1.5-2_aarch64.deb
libxext	1.3.7	aarch64	6e98a24e0d1996d25f7db8d70ecae02cfe5fc146343428a065149003454c7fc9	98008	pool/main/libx/libxext/libxext_1.3.7_aarch64.deb
libxml2	2.15.4-1	aarch64	d315861bbcf716cfb088f53cddab9fb6a96430cc66769f79774cc69c2f53bcff	442652	pool/main/libx/libxml2/libxml2_2.15.4-1_aarch64.deb
libxrender	0.9.13	aarch64	66b96ac572a9133836b638fb773b0dde4980541d9c49279a75a9ebace8f827c8	24728	pool/main/libx/libxrender/libxrender_0.9.13_aarch64.deb
libxshmfence	1.3.3-1	aarch64	7644c2969c2ce4d763785bd2a85eb32ccf8e5ad40228cd92b193f7edb6398d92	4548	pool/main/libx/libxshmfence/libxshmfence_1.3.3-1_aarch64.deb
libzimg	3.0.6	aarch64	a776d30cdb5734fa8feb17fb89fe8a67d14d64e491777d9b62b0fd714a9b59e8	139012	pool/main/libz/libzimg/libzimg_3.0.6_aarch64.deb
libzmq	4.3.5-2	aarch64	1d59efb56905e79159808c6b656cc768ffcc210012bc2d9b63f23162f65480d2	320404	pool/main/libz/libzmq/libzmq_4.3.5-2_aarch64.deb
littlecms	2.19.1	aarch64	274f732a186563beca204f5d016d30cac8e5c24f7c4395b60881f9613eddf1a1	143396	pool/main/l/littlecms/littlecms_2.19.1_aarch64.deb
mesa-vulkan-icd-swrast	26.2.5	aarch64	f7d72584111cb6ef5d2657ae9028626ac58ebb98cdac50ae1f3e313d6740e72c	1628908	pool/main/m/mesa-vulkan-icd-swrast/mesa-vulkan-icd-swrast_26.2.5_aarch64.deb
ncurses	6.6.20260307+really6.5.20250830	aarch64	f44bbfdc3d42ec0217bffa978309390e59cea5a48a9a83226d4a496c42ad0b99	557792	pool/main/n/ncurses/ncurses_6.6.20260307+really6.5.20250830_aarch64.deb
ncurses-ui-libs	6.6.20260307+really6.5.20250830	aarch64	7393f369009be189b3d4ec1f9b16ebd57621d6a1b22949ae07685573950d1f37	32940	pool/main/n/ncurses-ui-libs/ncurses-ui-libs_6.6.20260307+really6.5.20250830_aarch64.deb
ocl-icd	2.3.5	aarch64	2d76ddf09069ad599a4d5b2aee374c58411e1a3b0618b1ca5412467c9fd7b26a	104028	pool/main/o/ocl-icd/ocl-icd_2.3.5_aarch64.deb
openssl	1:3.6.5	aarch64	a2fb7856875e63ef6b90442752e05974813372c3ca86d2513a78ea43c67a0f8b	2482764	pool/main/o/openssl/openssl_1:3.6.5_aarch64.deb
pcre2	10.49	aarch64	c27995e5f52b8ecc9b8b3e662eb08e49f82a18bfd3f34343936acc7b23964724	1001320	pool/main/p/pcre2/pcre2_10.49_aarch64.deb
python	3.14.6-1	aarch64	3166e56c2b6c03fff41191fbb9d736302978e7c484702814d9f6dc99dd6006bd	4816756	pool/main/p/python/python_3.14.6-1_aarch64.deb
python-llvmlite	0.49.0-3	aarch64	ebee367165f9f5036a47d44b45704dff28956fba4149abd35c04c59d1c929771	22032852	pool/main/p/python-llvmlite/python-llvmlite_0.49.0-3_aarch64.deb
python-numpy	2.5.4	aarch64	a99ae20cd33c77553cc94d402aefc4bed96b7ec9f18e9fb6e2e5a7943693c802	3620880	pool/main/p/python-numpy/python-numpy_2.5.4_aarch64.deb
python-pip	26.2.1	all	92a9cb4b3c99dd20086f90fedc95c604eefc5bd0f88d1862690884474f82de44	1190440	pool/main/p/python-pip/python-pip_26.2.1_all.deb
python-scipy	1.18.1-1	aarch64	27900dbbc1db0d6fb63d2a2039d12b5af84cddf81d0d2cb27716dff6782cc710	12589288	pool/main/p/python-scipy/python-scipy_1.18.1-1_aarch64.deb
python-soxr	1.1.0-2	aarch64	323d99f19e5854c8312432e5778ce43dcdfd0b5f7db392632a7650833ae95409	81320	pool/main/p/python-soxr/python-soxr_1.1.0-2_aarch64.deb
python-torch	2.14.1-2	aarch64	cb5d96877f30bca10a0a19bcd32934a4f477ec7e5bfd00c2a82ac5c9e7d0eb73	36675500	pool/main/p/python-torch/python-torch_2.14.1-2_aarch64.deb
python-torchaudio	2.11.0-4	aarch64	54b02d1e68f142af1330da6fb318173082066473e4a7c8f570165ffa23b48723	216044	pool/main/p/python-torchaudio/python-torchaudio_2.11.0-4_aarch64.deb
python-torchcodec	0.17.0-1	aarch64	743240ce85592ed31f05e95e139490c5a94c3bc8fe3c519b32d52e1585a5117f	571432	pool/main/p/python-torchcodec/python-torchcodec_0.17.0-1_aarch64.deb
readline	8.3.6	aarch64	616cc73009bc0223f61caed8dd09455714455aa5ea5e180126e2f69c4c775136	294164	pool/main/r/readline/readline_8.3.6_aarch64.deb
resolv-conf	1.3	aarch64	ab541abac8e0c81709cd7ca4a02bcfa0d60ba1f4bfe7fd6dce4a694a4a9dfffa	976	pool/main/r/resolv-conf/resolv-conf_1.3_aarch64.deb
rubberband	4.0.0-1	aarch64	1172030a1e3ed70976114c8ca3eb4da0b82c1714825bd751ac1ada606dbc685a	205764	pool/main/r/rubberband/rubberband_4.0.0-1_aarch64.deb
svt-av1	4.2.0	aarch64	e1fd576d086e2d870429e3ae16610b24cb1d0c8f9fcf330fa0abba9e867aabdb	1490768	pool/main/s/svt-av1/svt-av1_4.2.0_aarch64.deb
ttf-dejavu	2.37-8	all	3fa9352d528cb19aebcdd2de5d1fb0cb67b201be3ae264207fc1a277d2cfd6da	2468280	pool/main/t/ttf-dejavu/ttf-dejavu_2.37-8_all.deb
vulkan-icd	0.1-1	all	d8d99b23502a3ff5952bc4d1c64375189c6aabce21729a96ccfee64677535329	740	pool/main/v/vulkan-icd/vulkan-icd_0.1-1_all.deb
vulkan-loader-generic	1.4.365	aarch64	99b22e01c966aa1e3dc4ab827508ccc256bebe3fafb20cf7c4883e965a7c3311	152808	pool/main/v/vulkan-loader-generic/vulkan-loader-generic_1.4.365_aarch64.deb
xorg-util-macros	1.20.2	all	11765ad1a6f181e36f807464f7b4360593d847dce245202a393eb2ca156520d0	21948	pool/main/x/xorg-util-macros/xorg-util-macros_1.20.2_all.deb
xorgproto	2026.1	all	2463651143a386eba0d7baebac87ca5d2db5239d36cf38f9b2086f3c1bfdcbce	249848	pool/main/x/xorgproto/xorgproto_2026.1_all.deb
xvidcore	1.3.7-1	aarch64	2f358b11fd750935b43ac19f09bb7c4228e007079426e0b73ee8bae1ddf26fc1	128616	pool/main/x/xvidcore/xvidcore_1.3.7-1_aarch64.deb
zlib	1.3.2	aarch64	75e7d0af17fcc3b40004309fdc00a1ddb9ae08346dce5e269902c34ac3966ac9	62840	pool/main/z/zlib/zlib_1.3.2_aarch64.deb
zstd	1.5.7-1	aarch64	e1b4a5113648da8de189620ba1fce74c48b2d0833d9043391b9a1c91fb606fd3	360488	pool/main/z/zstd/zstd_1.5.7-1_aarch64.deb
PINS
cp "$work/PINNED-APT.tsv" "$out/NEUTTS-PINNED-APT.tsv"
dpkg-query -W -f='${Package}\t${Version}\n' > "$out/NEUTTS-BASE-PACKAGES.tsv"
printf '%s\n' 'deb https://packages.termux.dev/apt/termux-main stable main' > "$PREFIX/etc/apt/sources.list"
apt_options=(-o Acquire::Retries=5 -o Dpkg::Options::=--force-confnew
             -o APT::Keep-Downloaded-Packages=true)
stage=signed-apt-update
apt-get "${apt_options[@]}" -o APT::Update::Error-Mode=any update
# The pinned image is an old rolling snapshot. Update its base before loading new
# native libraries; all scientific/runtime dependency packages are then pinned.
stage=rolling-base-upgrade
mkdir -p "$work/bootstrap/partial"
apt-get "${apt_options[@]}" -o Dir::Cache::archives="$work/bootstrap" -y --download-only dist-upgrade
shopt -s nullglob
bootstrap_debs=("$work/bootstrap/"*.deb)
if (("${#bootstrap_debs[@]}")); then
  sha256sum "${bootstrap_debs[@]}" > "$out/NEUTTS-BOOTSTRAP-ARCHIVES.sha256"
fi
apt-get "${apt_options[@]}" -o Dir::Cache::archives="$work/bootstrap" -y --no-download dist-upgrade
dpkg-query -W -f='${Package}\t${Version}\n' > "$out/NEUTTS-UPGRADED-BASE-PACKAGES.tsv"
[[ -e /bin/sh ]] || ln -s "$PREFIX/bin/sh" /bin/sh
rm -rf -- "$work/bootstrap"

stage=pinned-apt-download
mkdir -p "$work/archives/partial"
specs=()
while IFS=$'\t' read -r name version arch sha bytes archive_path; do
  specs+=("$name=$version")
done < "$work/PINNED-APT.tsv"
apt-get "${apt_options[@]}" -o Dir::Cache::archives="$work/archives" \
  -y --no-install-recommends --no-remove --download-only --reinstall install "${specs[@]}"
downloaded=("$work/archives/"*.deb)
[[ "${#downloaded[@]}" == "${#specs[@]}" ]] || { echo "APT added or omitted an unreviewed archive" >&2; exit 1; }
while IFS=$'\t' read -r name version arch sha bytes archive_path; do
  matches=("$work/archives/$name"_*.deb)
  [[ "${#matches[@]}" == 1 && -f "${matches[0]}" && ! -L "${matches[0]}" ]]
  file="${matches[0]}"
  [[ "$(stat -c %s "$file")" == "$bytes" ]]
  printf '%s  %s\n' "$sha" "$file" | sha256sum -c -
  [[ "$(dpkg-deb -f "$file" Package)" == "$name" ]]
  [[ "$(dpkg-deb -f "$file" Version)" == "$version" ]]
  [[ "$(dpkg-deb -f "$file" Architecture)" == "$arch" ]]
done < "$work/PINNED-APT.tsv"

stage=pinned-apt-install
apt-get "${apt_options[@]}" -o Dir::Cache::archives="$work/archives" \
  -y --no-install-recommends --no-remove --no-download --reinstall install "${specs[@]}"
dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' > "$out/NEUTTS-INSTALLED-PACKAGES.tsv"
while IFS=$'\t' read -r name version arch sha bytes archive_path; do
  [[ "$(dpkg-query -W -f='${Version}' "$name")" == "$version" ]]
done < "$work/PINNED-APT.tsv"
mkdir -p "$out/signed-apt"
for file in "$PREFIX/var/lib/apt/lists/"*_InRelease; do
  cp "$file" "$out/signed-apt/"
done
export LD_LIBRARY_PATH="$PREFIX/lib"

cat > "$work/native_core.py" <<'PY'
"""Real APT scientific behavior, with one isolated child per ABI boundary."""
import ctypes
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import traceback
import wave

CASES = ("torch", "torchaudio", "torchcodec", "scipy", "llvmlite", "soxr")
EXPECTED = {
    "torch": "2.14.1", "torchaudio": "2.11.0", "torchcodec": "0.17.0",
    "scipy": "1.18.1", "llvmlite": "0.49.0", "soxr": "1.1.0", "numpy": "2.5.4",
}


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def elf(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        header = stream.read(64)
    require(header[:6] == b"\x7fELF\x02\x01", "expected little-endian ELF64")
    machine = struct.unpack_from("<H", header, 18)[0]
    require(machine == 183, "expected actual AArch64 ELF")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path),
            "elf_class": 64, "endianness": "little", "machine": machine}


def libraries():
    prefix = Path(os.environ["PREFIX"])
    owners = {}
    for listing in (prefix / "var/lib/dpkg/info").glob("*.list"):
        for line in listing.read_text(errors="replace").splitlines():
            owners.setdefault(line, []).append(listing.name.removesuffix(".list"))
    paths = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        parts = line.split(None, 5)
        if len(parts) == 6 and parts[5].startswith("/") and ".so" in parts[5]:
            paths.add(parts[5])
    result = []
    for raw in sorted(paths):
        path = Path(raw)
        if path.is_file():
            identity = elf(path)
            identity["mapped_path"] = raw
            identity["dpkg_owners"] = sorted(set(owners.get(raw, []) + owners.get(str(path.resolve()), [])))
            result.append(identity)
    return result


def module_identity(module):
    name = module.__name__.split(".")[0]
    version = importlib.metadata.version(name)
    require(version.split("+", 1)[0] == EXPECTED[name], f"{name} distribution version differs")
    return {"distribution": name, "version": version, "module_file": module.__file__,
            "module_sha256": sha(module.__file__)}


def torch_case():
    import torch
    torch.set_num_threads(2)
    x = torch.arange(8, dtype=torch.float32).reshape(1, 1, 8)
    conv = torch.nn.Conv1d(1, 1, 3, bias=False)
    with torch.no_grad():
        conv.weight.copy_(torch.tensor([[[1.0, 2.0, 1.0]]]))
        result = conv(x).flatten().tolist()
    require(result == [4.0, 8.0, 12.0, 16.0, 20.0, 24.0], "Conv1d differs from exact stencil oracle")
    a = torch.tensor([[1.0, 2.0], [3.0, 4.0]])
    b = torch.tensor([[2.0, 0.0], [1.0, 2.0]])
    product = (a @ b).tolist()
    require(product == [[4.0, 4.0], [10.0, 8.0]], "tensor multiplication differs")
    return {"modules": [module_identity(torch)], "conv1d": result, "matmul": product, "device": str(x.device)}


def torchaudio_case():
    import torch
    import torchaudio
    torch.set_num_threads(2)
    signal = torch.tensor([math.sin(2 * math.pi * 1000 * i / 24000) for i in range(2400)])
    actual = torchaudio.functional.resample(signal, 24000, 16000)
    require(tuple(actual.shape) == (1600,) and bool(torch.isfinite(actual).all()), "resampled shape or values differ")
    expected = torch.tensor([math.sin(2 * math.pi * 1000 * i / 16000) for i in range(1600)])
    error = float(torch.mean(torch.abs(actual[64:-64] - expected[64:-64])))
    require(error < 0.005, "resampling differs from independent sinusoid oracle")
    return {"modules": [module_identity(torch), module_identity(torchaudio)],
            "input_rate": 24000, "output_rate": 16000, "output_samples": 1600, "mean_absolute_error": error}


def torchcodec_case(work):
    import torch
    import torchcodec
    from torchcodec.decoders import AudioDecoder
    pcm = [round(10000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(1600)]
    fixture = work / "owned-pcm.wav"
    with wave.open(str(fixture), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(struct.pack("<" + "h" * len(pcm), *pcm))
    decoded = AudioDecoder(str(fixture)).get_all_samples()
    require(decoded.sample_rate == 16000 and tuple(decoded.data.shape) == (1, 1600), "PCM decode shape/rate differs")
    expected = torch.tensor(pcm, dtype=torch.float32).reshape(1, -1) / 32768
    error = float(torch.max(torch.abs(decoded.data - expected)))
    require(bool(torch.isfinite(decoded.data).all()) and error < 0.000002, "decoded PCM differs from source samples")
    return {"modules": [module_identity(torch), module_identity(torchcodec)],
            "fixture_sha256": sha(fixture), "samples": 1600, "sample_rate": 16000, "maximum_absolute_error": error}


def scipy_case():
    import numpy as np
    import scipy
    from scipy import fft, linalg
    solved = linalg.solve(np.array([[3.0, 1.0], [1.0, 2.0]]), np.array([9.0, 8.0]))
    require(bool(np.allclose(solved, [2.0, 3.0], rtol=0, atol=1e-12)), "LAPACK solution differs")
    transformed = fft.fft(np.array([1.0, 2.0, 3.0, 4.0]))
    require(bool(np.allclose(transformed, [10.0, -2+2j, -2.0, -2-2j], rtol=0, atol=1e-12)), "FFT differs")
    return {"modules": [module_identity(np), module_identity(scipy)], "solution": solved.tolist(),
            "fft": [[float(x.real), float(x.imag)] for x in transformed]}


def llvmlite_case():
    import llvmlite
    from llvmlite import binding as llvm
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    triple = llvm.get_default_triple()
    target = llvm.Target.from_default_triple().create_target_machine()
    module = llvm.parse_assembly("""
define double @owned_mul_add(double %a, double %b) {
entry:
  %product = fmul double %a, %b
  %result = fadd double %product, 2.0
  ret double %result
}
""")
    module.triple = triple
    module.verify()
    with llvm.create_mcjit_compiler(module, target) as engine:
        engine.finalize_object()
        address = engine.get_function_address("owned_mul_add")
        require(address != 0, "JIT returned a null function")
        result = ctypes.CFUNCTYPE(ctypes.c_double, ctypes.c_double, ctypes.c_double)(address)(3.0, 7.0)
        require(result == 23.0, "native JIT function differs from independent arithmetic oracle")
    return {"modules": [module_identity(llvmlite)], "llvm_version": list(llvm.llvm_version_info),
            "target_triple": triple, "native_jit_result": result}


def soxr_case():
    import numpy as np
    import soxr
    signal = np.array([math.sin(2 * math.pi * 1000 * i / 24000) for i in range(2400)], dtype=np.float32)
    actual = soxr.resample(signal, 24000, 16000)
    require(actual.shape == (1600,) and bool(np.isfinite(actual).all()), "soxr shape/values differ")
    expected = np.array([math.sin(2 * math.pi * 1000 * i / 16000) for i in range(1600)])
    error = float(np.mean(np.abs(actual[64:-64] - expected[64:-64])))
    require(error < 0.005, "soxr differs from independent sinusoid oracle")
    return {"modules": [module_identity(np), module_identity(soxr)], "output_samples": 1600,
            "mean_absolute_error": error}


def run_case(name, out):
    receipt = {"schema_version": 1, "component": name, "status": "failed"}
    start = time.monotonic()
    try:
        result = torchcodec_case(Path(__file__).parent) if name == "torchcodec" else globals()[name + "_case"]()
        receipt.update(status="passed", behavior=result)
    except Exception as exc:
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        try:
            receipt["mapped_libraries"] = libraries()
        except Exception as exc:
            receipt.update(status="failed", library_evidence_error=str(exc))
        receipt["elapsed_seconds"] = round(time.monotonic() - start, 3)
        (out / f"neutts-{name}.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return 0 if receipt["status"] == "passed" else 1


def main(out):
    require(sys.platform == "android" and os.uname().machine == "aarch64" and os.getuid() == 1000,
            "native Bionic UID1000 interpreter required")
    require(sys.version_info[:3] == (3, 14, 6), "actual APT Python version differs")
    require(Path(sys.prefix).resolve() == Path(os.environ["PREFIX"]).resolve(), "probe entered a managed environment")
    packages = {}
    for line in (out / "NEUTTS-INSTALLED-PACKAGES.tsv").read_text().splitlines():
        name, version, architecture = line.split("\t")
        packages[name] = {"version": version, "architecture": architecture}
    pins = []
    for line in (out / "NEUTTS-PINNED-APT.tsv").read_text().splitlines():
        name, version, architecture, digest, size, filename = line.split("\t")
        require(packages.get(name) == {"version": version, "architecture": architecture}, "installed APT pin differs: " + name)
        pins.append({"package": name, "version": version, "architecture": architecture,
                     "sha256": digest, "bytes": int(size), "repository_path": filename})
    receipt = {
        "schema_version": 1, "status": "running", "scope": "APT-only native scientific ABI/behavior",
        "python": {"version": sys.version, "platform": sys.platform, "prefix": sys.prefix,
                   "executable": elf("/proc/self/exe")}, "uid": os.getuid(),
        "apt_archives": pins, "apt_archive_hashes_checked_before_install": True,
        "signed_apt": {p.name: sha(p) for p in (out / "signed-apt").iterdir()},
        "engine_installed": False, "synthesis_tested": False, "model_downloaded": False,
        "physical_audio_tested": False, "candidate_modified": False, "pm_admission_changed": False,
        "cases": [],
    }
    result_path = out / "NEUTTS-CORE-RESULT.json"
    for name in CASES:
        try:
            child = subprocess.run([sys.executable, "-I", "-B", __file__, "--case", name, str(out)],
                                   capture_output=True, timeout=90)
            code, stdout, stderr = child.returncode, child.stdout, child.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = 124, exc.stdout or b"", exc.stderr or b""
        (out / f"neutts-{name}.stdout.log").write_bytes(stdout[-100000:])
        (out / f"neutts-{name}.stderr.log").write_bytes(stderr[-100000:])
        path = out / f"neutts-{name}.json"
        result = json.loads(path.read_text()) if path.exists() else {"status": "failed", "error": "child exited without a receipt"}
        receipt["cases"].append({"component": name, "exit_code": code, "status": result["status"],
                                 "receipt": path.name if path.exists() else None,
                                 "receipt_sha256": sha(path) if path.exists() else None})
        result_path.write_text(json.dumps(receipt, indent=2) + "\n")
    receipt["status"] = "passed" if all(row["exit_code"] == 0 and row["status"] == "passed" for row in receipt["cases"]) else "failed"
    result_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "cases": receipt["cases"]}), flush=True)
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    if sys.argv[1] == "--case":
        raise SystemExit(run_case(sys.argv[2], Path(sys.argv[3])))
    raise SystemExit(main(Path(sys.argv[1])))
PY

stage=native-scientific-behavior
"$PREFIX/bin/python" -I -B "$work/native_core.py" "$out"
stage=complete
echo "NATIVE_APT_CORE_PASSED: dependency feasibility only; NeuTTS synthesis remains untested"
