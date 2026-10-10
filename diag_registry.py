import os, sys
os.environ['ML_MODEL_PATH'] = r'C:\Users\DELL\OneDrive\Desktop\Synapse PM\models\models'
sys.path.insert(0, r'C:\Users\DELL\OneDrive\Desktop\Synapse PM')

from app import ml_engine

print('=== REGISTRY ===')
print('Total loaded models:', len(ml_engine.models))
print('Total families:', len(ml_engine.by_family))
print()

print('=== PER-FAMILY MODEL COUNT ===')
for fam, mids in sorted(ml_engine.by_family.items()):
    print('  {}: {} models'.format(fam, len(mids)))
    for m in mids:
        print('      -', m)
print()

print('=== PROBE FAILURES (all of them) ===')
failures = ml_engine._probe_failures or {}
for mid, reason in failures.items():
    print('  DROPPED', mid)
    print('    reason:', reason)
print()
print('Total dropped:', len(failures))
print()

print('=== SAMPLE MODEL CONTRACTS (first 10) ===')
for mid in list(ml_engine.models)[:10]:
    info = ml_engine.models[mid]
    print(' ', mid)
    print('     feature_count =', info.get('feature_count'))
    print('     features      =', info.get('features'))
    print('     family        =', info.get('family'))
    print('     model_type    =', info.get('model_type'))
    print('     framework     =', info.get('framework'))
print()

print('=== datasets_industrial_pump_data specifically ===')
fam = 'datasets_industrial_pump_data'
if fam in ml_engine.by_family:
    print('  by_family[{}] = {}'.format(fam, ml_engine.by_family[fam]))
else:
    print('  NOT PRESENT in by_family')
if fam in ml_engine.all_by_family:
    print('  all_by_family[{}] = {}'.format(fam, ml_engine.all_by_family[fam]))
else:
    print('  NOT PRESENT in all_by_family')