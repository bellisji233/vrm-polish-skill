# Background runner: attach the expression studio to WORK/current.blend, run a code file with `helper`, save.
import importlib.util, sys, json, os
args = sys.argv[sys.argv.index('--') + 1:]
script, work, code_file = args[0], args[1], args[2]
spec = importlib.util.spec_from_file_location('expression_studio', script)
studio = importlib.util.module_from_spec(spec); sys.modules['expression_studio'] = studio; spec.loader.exec_module(studio)
helper = studio.attach(work)
ns = {'helper': helper, 'studio': studio, 'json': json}
exec(open(code_file, encoding='utf-8').read(), ns)
if not ns.get('NO_SAVE'):
    helper.save(export=bool(ns.get('EXPORT')))
print('RUN_OK')
