from pathlib import Path
import ast,hashlib,importlib.util,json
repo=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\termux-hermes-next-stable-20261017");base=Path(r"C:\Users\adyba\docker-chatgpt-devbox\workspace\neutts-complete-runtime-monitor-20261020\3f1f404\39456043425\independent-torchao-api-review");base.mkdir(parents=True,exist_ok=True)
deb=repo.parent/"neutts-frozen-foundation-recovery-20261020/foundation-host-inputs/apt-archives/python-torch_2.14.1-2_aarch64.deb"
path=repo/"scripts/prepare_neutts_perth_runtime.py"
assert hashlib.sha256(path.read_bytes()).hexdigest()=="7445bf89b0fd26f9f74a7935724e394b24b331409f200ecca9f2904ffacb40db"
spec=importlib.util.spec_from_file_location("_independent_torch_source_prep",path);prep=importlib.util.module_from_spec(spec);spec.loader.exec_module(prep)
lock=json.loads((repo/"scripts/neutts_complete_runtime_lock.json").read_bytes());torch=next(p for p in lock["apt_python"] if p["name"]=="torch")
facts,contents=prep.apt_python_payload(deb,torch["archive"],include_bytes=True)
assert all(facts[k]==torch[k] for k in facts),"Actual pinned APT payload facts changed"
wanted={
 "torch/_inductor/ir.py":["ChoiceCaller","FixedLayout","TensorBox","get_fill_order"],
 "torch/_inductor/lowering.py":["register_lowering","lowerings","make_fallback"],
 "torch/_inductor/select_algorithm.py":["ExternKernelChoice","autotune_select_algorithm","DataProcessorTemplateWrapper"],
 "torch/_inductor/codegen/cpp_flex_attention_template.py":["CppFlexAttentionTemplate"],
 "torch/_inductor/codegen/cpp_template.py":["CppTemplate"],
 "torch/_inductor/codegen/cpp_template_kernel.py":["parse_expr_with_index_symbols","wrap_with_tensorbox"],
 "torch/_inductor/utils.py":["parallel_num_threads"],
 "torch/_inductor/pattern_matcher.py":["Arg","CallFunction","KeywordArg","Match","PatternMatcherPass","register_lowering_pattern"],
 "torch/_inductor/custom_graph_pass.py":["CustomGraphPass","get_hash_for_files"],
 "torch/_dynamo/utils.py":["counters"],
 "torch/_inductor/kernel/flex/common.py":["construct_strides","maybe_realize"]}
def module_bindings(tree):
 out={}
 def visit(nodes):
  for n in nodes:
   if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
    out[n.name]=n
   elif isinstance(n,(ast.Import,ast.ImportFrom)):
    for a in n.names:out[a.asname or (a.name.split(".")[0] if isinstance(n,ast.Import) else a.name)]=n
   elif isinstance(n,ast.Assign):
    for t in n.targets:
     for x in ast.walk(t):
      if isinstance(x,ast.Name):out[x.id]=n
   elif isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name):out[n.target.id]=n
   elif isinstance(n,(ast.If,ast.Try,ast.With)):
    visit(n.body)
    if hasattr(n,"orelse"):visit(n.orelse)
    if hasattr(n,"finalbody"):visit(n.finalbody)
    if hasattr(n,"handlers"):
     for h in n.handlers:visit(h.body)
 visit(tree.body);return out
members=[];missing=[]
for member,names in wanted.items():
 raw=contents[member];source=raw.decode("utf-8");tree=ast.parse(source);bindings=module_bindings(tree);lines=source.splitlines()
 dst=base/"original-torch"/member;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
 symbols={}
 for name in names:
  node=bindings.get(name)
  if node is None:missing.append({"module":member,"symbol":name});continue
  symbols[name]={"line":node.lineno,"node_kind":type(node).__name__,"declaration":ast.unparse(node).splitlines()[0],"source_excerpt":"\n".join(lines[node.lineno-1:min(node.end_lineno,node.lineno+5)])}
 members.append({"path":member,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"requested_symbols":symbols})
old="torch/_inductor/kernel/flex_attention.py"
assert old not in contents and "torch/_inductor/kernel/flex_attention/__init__.py" not in contents,"Old module unexpectedly exists"
assert not missing,missing
value={"status":"passed","scope":"Bounded static source/symbol review of the directly reached TorchAO Inductor import path against all-facts-verified original signed Torch payload; no native runtime execution.","torch_archive":torch["archive"],"all_locked_torch_payload_facts_verified":True,"old_flex_attention_module_absent":True,"symbols_reviewed":sum(len(m["requested_symbols"]) for m in members),"modules_reviewed":len(members),"members":members,"missing_direct_import_symbols":missing,"guard_contract":"Only fallback for ModuleNotFoundError.name == torch._inductor.kernel.flex_attention; preserve ordinary ImportError and unrelated transitive ModuleNotFoundError.","moved_helper_call_shapes":{"construct_strides":"sizes, fill_order -> strides; original TorchAO call shape unchanged","maybe_realize":"list[IRNode|None] -> realized list; original TorchAO call shape unchanged"},"native_identity_and_operation_retry_required":True}
raw=(json.dumps(value,indent=2,sort_keys=True)+"\n").encode();out=base/"INDEPENDENT-TORCH-API-REVIEW.json";out.write_bytes(raw)
print(json.dumps({"path":str(out),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"modules":len(members),"symbols":value["symbols_reviewed"],"missing":missing}))
