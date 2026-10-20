"""Host integrity tests; never execute Android wheels or Perth models."""
from __future__ import annotations
import ast, copy, csv, gzip, hashlib, importlib.util, io, json, struct, tarfile, tempfile, unittest, zipfile
from pathlib import Path
from unittest import mock
ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit/neutts-perth-runtime-preparation-20261020"

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

prep = module("_test_perth_prepare", ROOT / "scripts/prepare_neutts_perth_runtime.py")
probe = module("_test_perth_probe", ROOT / "scripts/compatibility_probe_neutts_perth.py")

def ar_member(name, data):
    header = (name + "/").ljust(16) + "0".ljust(12) + "0".ljust(6) + "0".ljust(6)
    header += "100644".ljust(8) + str(len(data)).ljust(10) + "\x60\n"
    return header.encode("ascii") + data + (b"\n" if len(data) % 2 else b"")

def tar_bytes(entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, value, kind in entries:
            item = tarfile.TarInfo(name)
            item.mode = 0o644
            if kind == "file":
                item.size = len(value)
                archive.addfile(item, io.BytesIO(value))
            else:
                item.type = tarfile.SYMTYPE if kind == "link" else tarfile.FIFOTYPE
                item.linkname = value.decode() if kind == "link" else ""
                archive.addfile(item)
    return data.getvalue()

def synthetic_deb(entries=None, *, control=None, data_tar=None):
    """Explicitly synthetic hostile-header fixture, never native evidence."""
    control = control or b"Package: python-fixture\nVersion: 1\nArchitecture: aarch64\nDepends: python\n"
    control_tar = tar_bytes([("./control", control, "file")])
    if data_tar is None:
        prefix = "./" + prep.SITE_PREFIX
        entries = entries if entries is not None else [
            (prefix + "fixture/__init__.py", b"VALUE = 1\n", "file"),
            (prefix + "fixture-1.dist-info/METADATA",
             b"Metadata-Version: 2.1\nName: fixture\nVersion: 1\nRequires-Python: >=3.10\n", "file"),
            (prefix + "fixture-1.dist-info/WHEEL",
             b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp314-cp314-android_aarch64\n", "file"),
            (prefix + "fixture-1.dist-info/RECORD", b"unchanged original fixture record\n", "file")]
        data_tar = tar_bytes(entries)
    raw = b"!<arch>\n" + ar_member("debian-binary", b"2.0\n")
    raw += ar_member("control.tar.gz", gzip.compress(control_tar, mtime=0))
    raw += ar_member("data.tar.gz", gzip.compress(data_tar, mtime=0))
    return raw, {"name":"python-fixture","version":"1","architecture":"aarch64",
        "filename":"pool/main/p/python-fixture/python-fixture_1_aarch64.deb","bytes":len(raw),
        "sha256":hashlib.sha256(raw).hexdigest(),"depends":"python","pre_depends":""}

class FrozenInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock, cls.raw = prep.load_lock()

    def test_exact_graph_counts_and_declared_scope(self):
        closure = json.loads((AUDIT / "declared-runtime-closure.json").read_bytes())
        self.assertEqual(self.lock["nodes"], closure["nodes"])
        self.assertEqual(self.lock["edges"], closure["edges"])
        self.assertEqual((len(self.lock["nodes"]), len(self.lock["edges"])), (43,50))
        self.assertEqual((len(self.lock["packages"]),len(self.lock["apt_python"])), (36,7))
        self.assertEqual(self.lock["foundation_support_outside_graph"], ["pip","torchcodec"])
        self.assertTrue(all(value is False for value in self.lock["boundaries"].values()))

    def test_exact_support_sources_and_local_large_payload_limits(self):
        for pin in self.lock["source_files"]:
            with self.subTest(path=pin["path"]):
                self.assertEqual(len(prep.verified_bytes(ROOT/pin["path"],pin)),pin["bytes"])
        self.assertEqual(prep.MAX_APT_MEMBER_BYTES,128*1024*1024)
        self.assertEqual(prep.MAX_APT_PAYLOAD_BYTES,256*1024*1024)
        self.assertEqual(prep.wheel_helper().MAX_MEMBER_BYTES,64*1024*1024)
        sources = {p["name"]:p for p in self.lock["apt_python"]}
        self.assertEqual(max(p["bytes"] for p in sources["torch"]["files"]),123615448)
        self.assertEqual(max(p["bytes"] for p in sources["llvmlite"]["files"]),112487040)

    def test_all_original_apt_metadata_and_record_files_are_retained(self):
        for package in self.lock["apt_python"]:
            with self.subTest(name=package["name"]):
                self.assertEqual(package["metadata_sha256"],package["original_apt_ledger"]["metadata"]["sha256"])
                self.assertEqual(package["distribution"]["wheel_tags"],package["original_apt_ledger"]["wheel"]["tags"])
                self.assertEqual(package["file_count"],len(package["files"]))
                self.assertEqual(package["bytes"],sum(p["bytes"] for p in package["files"]))
                self.assertEqual(len([p for p in package["files"] if p["path"].endswith(".dist-info/RECORD")]),1)

    def test_actual_native_wheels_records_elf_and_original_licenses(self):
        for package in self.lock["packages"]:
            if package["origin"]["kind"] != "native-handoff": continue
            with self.subTest(name=package["name"]):
                path=ROOT/package["origin"]["retained_path"]
                facts=prep.verify_wheel(path,package)
                self.assertTrue(facts["native_members"])
                with zipfile.ZipFile(path) as archive:
                    self.assertIsNone(archive.testzip())
                    for pin in facts["native_members"]:
                        raw=archive.read(pin["member"])
                        self.assertEqual(raw[:6],b"\x7fELF\x02\x01")
                        self.assertEqual(struct.unpack_from("<HH",raw,16),(3,183))
                        self.assertEqual(hashlib.sha256(raw).hexdigest(),pin["sha256"])
                    for pin in package["origin"]["original_license_members"]:
                        raw=archive.read(pin["path"])
                        self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(pin["bytes"],pin["sha256"]))

    def test_three_component_receipts_bind_original_successful_builds(self):
        for name in ("audioop-lts","pyyaml","scikit-learn"):
            package=next(p for p in self.lock["packages"] if p["name"]==name)
            origin=package["origin"]
            result=json.loads(prep.verified_bytes(ROOT/origin["build_receipt"]["path"],origin["build_receipt"]))
            runtime=json.loads(prep.verified_bytes(ROOT/origin["runtime_receipt"]["path"],origin["runtime_receipt"]))
            self.assertEqual((result["status"],result["stage"]),("passed","complete"))
            self.assertEqual(runtime["status"],"passed")
            self.assertEqual(result["wheel"]["artifact"],package["artifact"])
            self.assertEqual(result["runtime"]["receipt_sha256"],origin["runtime_receipt"]["sha256"])

    def test_four_handoffs_are_original_outputs_not_new_runtime_claims(self):
        selected=[p for p in self.lock["packages"] if p["origin"]["kind"]=="native-handoff"]
        self.assertEqual({p["name"] for p in selected},prep.NATIVE_NAMES)
        self.assertEqual(sum(p["artifact"]["bytes"] for p in selected),17481715)
        report=json.loads((AUDIT/"HOST-INPUT-REVIEW.json").read_bytes())
        self.assertFalse(report["native_runtime_tested"])
        self.assertFalse(report["release_output"])
        self.assertTrue(report["whole_source_artifact_hashes_verified"])
        self.assertTrue(report["selected_zip_members_crc_checked"])

    def test_lock_identity_tampering_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/prep.LOCK_FILENAME
            path.write_bytes(self.raw+b" ")
            with self.assertRaisesRegex(prep.PrepareError,"lock changed"): prep.load_lock(path)

    def test_semantic_scope_expansions_are_refused(self):
        for field,mutate in (
            ("names",lambda d:d["names"].append("unreviewed")),
            ("edge_count",lambda d:d.update(edge_count=49)),
            ("extras",lambda d:d.update(selected_extras=["gpu"])),
            ("install",lambda d:d["apt_install"].append(d["apt_provenance_only"][0])),
            ("support",lambda d:d.update(foundation_support_outside_graph=[])),
            ("bounds",lambda d:d["limits"].update(apt_member_bytes=129*1024*1024)),
            ("release",lambda d:d["boundaries"].update(release_output=True))):
            with self.subTest(field=field):
                changed=copy.deepcopy(self.lock);mutate(changed)
                with self.assertRaises(prep.PrepareError): prep.validate_lock(changed)

class OriginalAPTReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock,_=prep.load_lock()
        cls.original=next(p for p in cls.lock["apt_python"] if p["name"]=="msgpack")
        cls.path=AUDIT/"fixtures/python-msgpack_1.2.3_aarch64.deb"

    def read_synthetic(self,raw,pin):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"fixture.deb";path.write_bytes(raw)
            return prep.apt_python_payload(path,pin,include_bytes=True)

    def test_real_original_signed_msgpack_full_payload_and_control(self):
        self.assertEqual(len(prep.verified_bytes(self.path,self.original["archive"])),61724)
        facts,contents=prep.apt_python_payload(self.path,self.original["archive"],include_bytes=True)
        self.assertTrue(all(facts[key]==self.original[key] for key in facts))
        self.assertEqual((len(contents),sum(map(len,contents.values()))),(13,198321))
        prep.apt_helper().verify_snapshot(ROOT/"audit/neutts-runtime-index-20261017",
                                        self.lock["apt_install"]+self.lock["apt_provenance_only"])

    def test_real_archive_corruption_refused_before_extraction(self):
        raw=bytearray(self.path.read_bytes());raw[-10]^=1
        with self.assertRaisesRegex(prep.PrepareError,"identity differs"):
            self.read_synthetic(raw,self.original["archive"])

    def test_synthetic_payload_keeps_metadata_and_record(self):
        raw,pin=synthetic_deb();facts,contents=self.read_synthetic(raw,pin)
        self.assertEqual(facts["file_count"],4)
        self.assertEqual(facts["distribution"]["name"],"fixture")
        self.assertEqual(contents["fixture-1.dist-info/RECORD"],b"unchanged original fixture record\n")

    def test_control_identity_and_duplicate_fields_are_refused(self):
        for control in (
            b"Package: python-fixture\nPackage: python-fixture\nVersion: 1\nArchitecture: aarch64\nDepends: python\n",
            b"Package: python-fixture\nVersion: 2\nArchitecture: aarch64\nDepends: python\n",
            b"Package: python-fixture\nVersion: 1\nArchitecture: amd64\nDepends: python\n",
            b"Package: python-fixture\nVersion: 1\nArchitecture: aarch64\nDepends: python, unreviewed\n"):
            with self.subTest(control=control):
                raw,pin=synthetic_deb(control=control)
                with self.assertRaises(prep.PrepareError): self.read_synthetic(raw,pin)

    def test_tar_traversal_alias_duplicate_and_special_headers_are_refused(self):
        prefix="./"+prep.SITE_PREFIX
        cases=[
            [("../../escape",b"x","file")],[(prefix+"../escape",b"x","file")],
            [(prefix+"alias",b"/outside","link")],[(prefix+"pipe",b"","fifo")],
            [(prefix+"same",b"a","file"),(prefix+"same",b"b","file")],
            [(prefix+"upper",b"a","file"),(prefix+"UPPER",b"b","file")]]
        for entries in cases:
            with self.subTest(entries=entries):
                raw,pin=synthetic_deb(entries)
                with self.assertRaises((prep.PrepareError,prep.wheel_helper().PrepareError)):
                    self.read_synthetic(raw,pin)

    def test_large_real_tar_header_is_refused_before_read(self):
        member=tarfile.TarInfo("./"+prep.SITE_PREFIX+"oversized.so")
        member.size=prep.MAX_APT_MEMBER_BYTES+1
        raw,pin=synthetic_deb(data_tar=member.tobuf(format=tarfile.USTAR_FORMAT)+b"\0"*1024)
        with self.assertRaisesRegex(prep.PrepareError,"finite bound"): self.read_synthetic(raw,pin)

    def test_real_fixture_member_and_total_caps_are_enforced(self):
        for name,limit in (("MAX_APT_MEMBER_BYTES",145799),("MAX_APT_PAYLOAD_BYTES",198320)):
            with self.subTest(name=name),mock.patch.object(prep,name,limit):
                with self.assertRaisesRegex(prep.PrepareError,"finite bound"):
                    prep.apt_python_payload(self.path,self.original["archive"])

    def test_archive_sha_size_and_missing_file_are_refused(self):
        for key,value in (("bytes",61723),("sha256","0"*64)):
            changed=dict(self.original["archive"]);changed[key]=value
            with self.subTest(key=key),self.assertRaises(prep.PrepareError):
                prep.apt_python_payload(self.path,changed)
        with self.assertRaises(OSError):
            prep.apt_python_payload(self.path.with_name("missing.deb"),self.original["archive"])

class ClosureAndPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock,cls.raw=prep.load_lock()
        cls.distributions={p["name"]:{k:p[k] for k in ("version","requires_python","requires_dist")}
                           for p in cls.lock["packages"]+cls.lock["apt_python"]}

    def test_original_metadata_recomputes_exact_43_50_graph(self):
        report=probe.validate_closure(self.lock,self.distributions,self.lock["environment"])
        self.assertEqual((report["node_count"],report["active_edge_count"]),(43,50))
        self.assertFalse(report["global_site_visible"]);self.assertFalse(report["metadata_modified"])

    def test_missing_and_extra_distribution_rejected(self):
        changed=copy.deepcopy(self.distributions);changed.pop("soundfile")
        with self.assertRaises(probe.ProbeError): probe.validate_closure(self.lock,changed,self.lock["environment"])
        changed["unreviewed"]={"version":"1","requires_dist":[],"requires_python":""}
        with self.assertRaises(probe.ProbeError): probe.validate_closure(self.lock,changed,self.lock["environment"])

    def test_interpreter_and_full_declared_dependencies_cannot_be_relaxed(self):
        for name,key,value in (("numba","requires_python",">=3.8"),("librosa","requires_dist",[]),
                               ("scipy","version","1.18.2"),("resemble-perth","requires_dist",["unreviewed"])):
            with self.subTest(name=name,key=key):
                changed=copy.deepcopy(self.distributions);changed[name][key]=value
                with self.assertRaises(probe.ProbeError): probe.validate_closure(self.lock,changed,self.lock["environment"])

    def test_inactive_extra_clause_is_preserved(self):
        changed=copy.deepcopy(self.distributions);changed["audioread"]["requires_dist"].pop(0)
        with self.assertRaises(probe.ProbeError): probe.validate_closure(self.lock,changed,self.lock["environment"])

    def test_foreign_marker_environment_and_dropped_edge_rejected(self):
        for key,value in (("sys_platform","linux"),("python_full_version","3.13.0"),
                          ("platform_machine","x86_64")):
            with self.subTest(key=key):
                env=dict(self.lock["environment"]);env[key]=value
                with self.assertRaises(probe.ProbeError): probe.validate_closure(self.lock,self.distributions,env)
        altered=copy.deepcopy(self.lock);altered["edges"].pop()
        with self.assertRaises(probe.ProbeError): probe.validate_closure(altered,self.distributions,self.lock["environment"])

    def test_exact_original_two_package_plan_passes(self):
        text="Inst libyaml (0.2.5-5 localhost [aarch64])\nInst python-msgpack (1.2.3 localhost [aarch64])\n"
        self.assertEqual(probe.validate_install_plan(text,self.lock["apt_install"])["packages"],
                         {"libyaml":"0.2.5-5","python-msgpack":"1.2.3"})

    def test_removal_addition_version_drift_and_duplicate_plan_rejected(self):
        original="Inst libyaml (0.2.5-5 repo [aarch64])\nInst python-msgpack (1.2.3 repo [aarch64])\n"
        for changed in (original+"Remv python [3.14.6-1]\n",original+"Inst compiler (1 repo [aarch64])\n",
                        original.replace("1.2.3 ","1.2.4 "),original+"Inst libyaml (0.2.5-5 repo [aarch64])\n",
                        original.splitlines()[0]+"\n","Inst libyaml unknown\n"):
            with self.subTest(changed=changed),self.assertRaises(probe.ProbeError):
                probe.validate_install_plan(changed,self.lock["apt_install"])

    def test_prepared_receipt_binds_downloads_and_false_flags(self):
        wheels=[{k:v for k,v in p.items() if k not in ("origin","frozen_graph_requires_dist")}
                for p in self.lock["packages"]]
        rows=[{"filename":prep.apt_helper().archive_name(p),"origin_url":prep.apt_helper().ORIGIN+p["filename"],
               "method":"verified-retained-cache","cache_path":"synthetic-host-policy-fixture",
               "bytes":p["bytes"],"sha256":p["sha256"]} for p in prep.extra_apt_pins(self.lock)]
        receipt=prep.receipt_for(self.lock,self.raw,wheels,rows)
        self.assertEqual(prep.verify_prepared_receipt(receipt,self.lock,self.raw,wheels),receipt)
        variations=[
            lambda r:r["apt_downloads"].pop(),
            lambda r:r["apt_downloads"].append(dict(r["apt_downloads"][0])),
            lambda r:r["apt_downloads"][0].update(sha256="0"*64),
            lambda r:r["apt_downloads"][0].update(origin_url="https://wrong.example/a.deb"),
            lambda r:r["apt_downloads"][0].update(method="original-https-archive",effective_url="http://wrong/a.deb")]
        variations += [lambda r,name=name:r.update({name:True}) for name in prep.FALSE_FLAGS]
        for mutate in variations:
            changed=copy.deepcopy(receipt);mutate(changed)
            with self.subTest(flags=changed["release_output"]),self.assertRaises(prep.PrepareError):
                prep.verify_prepared_receipt(changed,self.lock,self.raw,wheels)

    def test_disconnected_inspection_and_actual_limits_required(self):
        image="sha256:"+"1"*64
        good={"schema_version":1,"status":"disconnected","release_output":False,"container":{
            "Image":image,"State":{"Running":True},"NetworkSettings":{"Networks":{}},
            "Config":{"User":"1000:1000","Hostname":"fixture"},
            "HostConfig":{"NanoCpus":2000000000,"Memory":6442450944,"PidsLimit":512}}}
        self.assertEqual(probe.validate_network_inspection(good,image,"fixture"),good["container"])
        for group,field,value in (("NetworkSettings","Networks",{"bridge":{}}),("Config","User","0:0"),
            ("Config","Hostname","different"),("State","Running",False),("HostConfig","Memory",0),
            ("HostConfig","PidsLimit",0),("HostConfig","NanoCpus",0)):
            with self.subTest(group=group,field=field):
                changed=copy.deepcopy(good);changed["container"][group][field]=value
                with self.assertRaises(probe.ProbeError): probe.validate_network_inspection(changed,image,"fixture")

class MainCandidateSelectionTests(unittest.TestCase):
    """Synthetic AR/tar streaming cases; not a claim about a native release artifact."""
    def fixture(self, *, omit=None, duplicate=False, corrupt=False):
        helper = prep.load_module("_test_perth_main_extract", ROOT / "scripts/extract_phonemizer_catalog.py",
                                  prep.EXTRACT_HELPER_SHA256)
        catalog = b'{"schema_version":1,"fixture_only":true}\n'
        packages, entries = [], [(helper.PAYLOAD + "bundled-wheels.json", catalog, "file")]
        for index in range(8):
            name = "fixture-" + str(index)
            filename = name + ".whl"
            raw = ("non-executable synthetic wheel bytes " + str(index)).encode()
            package = {"name": name, "artifact": {"filename": filename, "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest()},
                "origin": {"kind": "main-catalog", "catalog_record": {"file": "wheels/" + filename}}}
            packages.append(package)
            if omit != index:
                entries.append((helper.PAYLOAD + package["origin"]["catalog_record"]["file"],
                                b"X" * len(raw) if corrupt and index == 0 else raw, "file"))
        if duplicate:
            entries.append(entries[-1])
        archive = b"!<arch>\n" + ar_member("debian-binary", b"2.0\n")
        archive += ar_member("data.tar.gz", gzip.compress(tar_bytes(entries), mtime=0))
        lock = {"packages": packages, "main_catalog": {"bytes": len(catalog),
            "sha256": hashlib.sha256(catalog).hexdigest()},
            "main_deb": {"bytes": len(archive), "sha256": hashlib.sha256(archive).hexdigest()}}
        return archive, lock, catalog

    def test_stream_selects_exact_catalog_and_eight_original_members(self):
        raw, lock, catalog = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); path = root / "fixture.deb"; path.write_bytes(raw)
            prep.extract_main(path, lock, root / "selected")
            selected = root / "selected"
            self.assertEqual((selected / "main-bundled-wheels.json").read_bytes(), catalog)
            self.assertEqual(len(list((selected / "wheels").iterdir())), 8)
            for package in lock["packages"]:
                value = (selected / "wheels" / package["artifact"]["filename"]).read_bytes()
                self.assertEqual(hashlib.sha256(value).hexdigest(), package["artifact"]["sha256"])

    def test_stream_refuses_missing_duplicate_or_changed_selected_input(self):
        for kwargs in ({"omit": 0}, {"duplicate": True}, {"corrupt": True}):
            with self.subTest(case=kwargs), tempfile.TemporaryDirectory() as temporary:
                raw, lock, _ = self.fixture(**kwargs)
                root = Path(temporary); path = root / "fixture.deb"; path.write_bytes(raw)
                with self.assertRaises(prep.PrepareError):
                    prep.extract_main(path, lock, root / "selected")

    def test_stream_requires_whole_candidate_identity_before_selection(self):
        raw, lock, _ = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); path = root / "fixture.deb"; path.write_bytes(raw)
            lock["main_deb"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(prep.PrepareError, "main .deb identity"):
                prep.extract_main(path, lock, root / "selected")


class StaticNativeInspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock, _ = prep.load_lock()

    def test_actual_retained_native_wheels_use_static_elf_without_execution(self):
        names = {"numba", "audioop-lts", "pyyaml", "scikit-learn"}
        count = 0
        with tempfile.TemporaryDirectory() as temporary:
            for package in self.lock["packages"]:
                if package["name"] not in names:
                    continue
                archive = AUDIT / "native-wheels" / package["artifact"]["filename"]
                with zipfile.ZipFile(archive) as wheel:
                    for member in package["native_members"]:
                        with self.subTest(package=package["name"], member=member["member"]):
                            raw = wheel.read(member["member"])
                            self.assertEqual(hashlib.sha256(raw).hexdigest(), member["sha256"])
                            path = Path(temporary) / package["name"] / member["member"]
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(raw)
                            value = probe.native_elf(path, dynamic=True)
                            self.assertEqual(value["sha256"], member["sha256"])
                            self.assertEqual(value["bytes"], member["bytes"])
                            self.assertEqual((value["class"], value["machine"], value["endianness"]),
                                             (64, 183, "little"))
                            self.assertIn("no readelf or binary execution", value["inspection"])
                            self.assertTrue(value["needed"])
                            count += 1
        self.assertEqual(count, 83)

    def test_actual_original_msgpack_extension_static_identity(self):
        package = next(p for p in self.lock["apt_python"] if p["name"] == "msgpack")
        pin = package["archive"]
        archive = AUDIT / "fixtures" / prep.apt_helper().archive_name(pin)
        facts, contents = prep.apt_python_payload(archive, pin, include_bytes=True)
        natives = [row for row in facts["files"] if row["path"].endswith(".so")]
        self.assertEqual(len(natives), 1)
        row = natives[0]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "original-msgpack.so"
            path.write_bytes(contents[row["path"]])
            value = probe.native_elf(path, dynamic=True)
            self.assertEqual(value["sha256"], row["sha256"])
            self.assertEqual(value["bytes"], row["bytes"])
            self.assertIn("libpython3.14.so", value["needed"])


    def test_global_python_native_payloads_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(probe, "PREFIX", Path(temporary)/"base"):
            allowed=[{"classification":"apt-library",
                      "resolved_path":str(probe.PREFIX/"lib/libsndfile.so.1")}]
            self.assertIsNone(probe.validate_mapping_classes(allowed))
            global_row={"classification":"apt-library",
                        "resolved_path":str(probe.PREFIX/"lib/python3.14/site-packages/torch/lib/libtorch_cpu.so")}
            with self.assertRaisesRegex(probe.ProbeError,"global Python"):
                probe.validate_mapping_classes([global_row])
            with self.assertRaisesRegex(probe.ProbeError,"Foreign"):
                probe.validate_mapping_classes([{"classification":"rejected-foreign",
                                                   "resolved_path":str(Path(temporary)/"unexpected.so")}])
            child=Path(temporary)/"isolated"
            self.assertEqual(probe.isolated_native_library_path(child),
                str(child/"lib/python3.14/site-packages/torch/lib")+probe.os.pathsep+str(probe.PREFIX/"lib"))

    def test_mapping_inspection_does_not_request_compiler_tools(self):
        source = (ROOT / "scripts/compatibility_probe_neutts_perth.py").read_text()
        self.assertNotIn("common.elf(", source)
        self.assertNotIn("common.verify_mapped_apt_libraries(", source)
        self.assertIn("common.ar_data_members(archive, pin, wanted)", source)
        self.assertIn('snapshot.get(package) == {"version": pin["version"]', source)
        self.assertIn('path.read_bytes() == raw', source)
        self.assertIn("types.SimpleNamespace(package_snapshot=common.package_snapshot, elf=native_elf)", source)
        self.assertEqual(probe.ELF_SHA256, hashlib.sha256(
            (ROOT / "scripts/neutts_runtime_elf.py").read_bytes()).hexdigest())


class RuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/"scripts/compatibility_probe_neutts_perth.py").read_text()
        cls.tree=ast.parse(cls.source)
        cls.shell=(ROOT/"scripts/compatibility_probe_neutts_perth.sh").read_text()
        cls.workflow=(ROOT/".github/workflows/neutts-perth-component.yml").read_text()

    def test_safe_checkpoint_and_strict_state_are_literal_requirements(self):
        calls=[n for n in ast.walk(self.tree) if isinstance(n,ast.Call)]
        loads=[n for n in calls if isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
               and n.func.value.id=="torch" and n.func.attr=="load"]
        self.assertEqual(len(loads),1)
        self.assertEqual({k.arg:ast.literal_eval(k.value) for k in loads[0].keywords},
                         {"weights_only":True,"map_location":"cpu"})
        strict=[n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=="load_state_dict"]
        self.assertEqual(len(strict),1)
        self.assertEqual({k.arg:ast.literal_eval(k.value) for k in strict[0].keywords},{"strict":True})
        self.assertNotIn("add_safe_globals",self.source)
        self.assertNotIn("weights_only=False",self.source)

    def test_real_public_injection_and_soundfile_calls_required(self):
        calls=[n for n in ast.walk(self.tree) if isinstance(n,ast.Call)]
        constructors=[n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=="PerthImplicitWatermarker"]
        self.assertEqual(len(constructors),1)
        values={k.arg:k.value for k in constructors[0].keywords}
        self.assertIsNone(ast.literal_eval(values["run_name"]))
        self.assertEqual(ast.literal_eval(values["device"]),"cpu")
        self.assertEqual(values["perth_net"].id,"model")
        self.assertIn('sf.write(buffer, signal, rate, format="WAV", subtype="FLOAT")',self.source)
        self.assertIn("roundtrip.tobytes() == original",self.source)
        self.assertIn("get_watermark(samples, rate, round=False)",self.source)
        self.assertIn("get_watermark(samples, rate, round=True)",self.source)
        self.assertIn('"quality_threshold_asserted": False',self.source)

    def test_inventory_surrounds_operations_and_thread_setup_precedes_work(self):
        runtime=next(n for n in self.tree.body if isinstance(n,ast.FunctionDef) and n.name=="runtime_case")
        text=ast.get_source_segment(self.source,runtime)
        self.assertEqual(text.count("nr.installed_inventory("),2)
        self.assertEqual(text.count("installed_records("),2)
        self.assertLess(text.index("torch.set_num_interop_threads(2)"),text.index("auxiliary_operations()"))
        self.assertLess(text.index('report["installed_before"]'),text.index("perth_operations("))
        self.assertGreater(text.index('report["installed_after"]'),text.index("perth_operations("))
        self.assertNotIn("sys.modules[",self.source)

    def test_shell_offline_barrier_preserves_foundation_and_readonly_inputs(self):
        self.assertIn("bash /probes/scripts/compatibility_probe_neutts.sh --in-container",self.shell)
        self.assertIn("neutts_apt_snapshot_open",self.shell)
        self.assertIn('docker network disconnect bridge "$container"',self.shell)
        for name in ("python-wheelhouse","foundation-apt-inputs","perth-inputs"):
            self.assertIn('-v "$out/'+name+':/out/'+name+':ro"',self.shell)
        self.assertIn("--cpus 2 --memory 6g --pids-limit 512",self.shell)
        self.assertIn("--user 1000:1000",self.shell)
        self.assertIn("--network bridge",self.shell)
        self.assertIn('values[0].get("Id") != container_id',self.shell)
        self.assertIn('container_id = (out / "PERTH-CONTAINER-ID.txt").read_text().strip()',self.shell)
        self.assertIn('[[ -f "$out/PERTH-NETWORK-DISCONNECTED.json" ]]',self.shell)
        self.assertNotIn("--allow-unauthenticated",self.shell)
        self.assertNotIn("--allow-downgrades",self.shell)


    def test_actual_host_offline_signal_binds_created_container_id(self):
        # Execute only the host JSON handoff block on explicit synthetic inspect data.
        # This does not contact Docker or claim an actually disconnected native process.
        block = self.shell.split("<<'PY_NETWORK'\n", 1)[1].split("\nPY_NETWORK", 1)[0]
        cases = (("matching", "a" * 64, {}, True),
                 ("wrong-created-id", "b" * 64, {}, False),
                 ("still-connected", "a" * 64, {"bridge": {}}, False))
        for label, inspected_id, networks, success in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "PERTH-CONTAINER-ID.txt").write_text("a" * 64 + "\n")
                value = [{"Id": inspected_id, "State": {"Running": True},
                          "NetworkSettings": {"Networks": networks}}]
                (root / "PERTH-DISCONNECTED-CONTAINER.json").write_text(json.dumps(value))
                result = probe.subprocess.run([probe.sys.executable, "-B", "-c", block, str(root)],
                                               capture_output=True, text=True, timeout=15)
                signal = root / "PERTH-NETWORK-DISCONNECTED.json"
                self.assertEqual(result.returncode == 0, success)
                self.assertEqual(signal.exists(), success)
                if success:
                    self.assertEqual(json.loads(signal.read_text())["container"]["Id"], "a" * 64)

    def test_workflow_read_permissions_pinned_actions_and_no_release(self):
        for value in ("contents: read","actions: read","GH_TOKEN: ${{ github.token }}",
            "runs-on: ubuntu-24.04-arm","actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a","persist-credentials: false",
            "include-hidden-files: true","tests/test_neutts_perth_runtime.py"):
            self.assertIn(value,self.workflow)
        self.assertNotIn("contents: write",self.workflow)
        self.assertNotIn("gh release",self.workflow)

    def test_module_source_bindings_are_current(self):
        self.assertEqual(probe.PREPARER_SHA256,hashlib.sha256(
            (ROOT/"scripts/prepare_neutts_perth_runtime.py").read_bytes()).hexdigest())
        self.assertEqual(probe.NONRUST_SHA256,hashlib.sha256(
            (ROOT/"scripts/compatibility_probe_neutts_nonrust.py").read_bytes()).hexdigest())

if __name__=="__main__": unittest.main()
