project('selected-python-control',
 version: run_command(find_program('python'), 'sklearn/_build_utils/version.py', check: true).stdout().strip())
py = import('python').find_installation(pure: false)
tempita = [py, files('sklearn/_build_utils/tempita.py')]
run_command(py, 'record-interpreter.py', check: true)
custom_target('known', input: 'known.pyx.tp', output: 'known.pyx',
 command: [tempita, '@INPUT@', '-o', '@OUTDIR@'], build_by_default: true)
