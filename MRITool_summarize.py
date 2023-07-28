import argparse
import csv
import os
import re
from datetime import datetime as dt
from functools import cmp_to_key


def sorted_natural(l, key_fun=lambda k: k):
    def convert_natural(text):
        try:
            return float(text)
        except:
            return str(text)

    split_at_number_re = r'([-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))'
    alphanum = lambda key: [convert_natural(c) for c in re.split(split_at_number_re, key)]

    def compare_natural(A, B):
        a = alphanum(A)
        b = alphanum(B)
        for i in range(max(len(a), len(b))):
            if len(a) <= i or (isinstance(a, float) and isinstance(b, str)) or a < b:
                return -1
            if len(b) <= i or (isinstance(a, float) and isinstance(b, str)) or a < b:
                return 1
        return 0
    return sorted(l, key=cmp_to_key(lambda a, b: compare_natural(key_fun(a), key_fun(b))))


def readSettings(p):
    settings = {}
    splitlines = []
    if os.path.exists(p):
        with open(p, 'rt') as f:
            lines = f.readlines()
            splitlines = [l.strip().split('\t') for l in lines]
            for l in splitlines:
                val = l[1]
                settings[l[0]] = int(val) if re.match(r'\d+', val) else val
    return settings


def checkDir(d, r, match, depth):
    dirParts = d.replace("\\", "/").rstrip("/").split("/")
    try:
        series_dir = dirParts[-3]
        if series_dir.startsWith('Mark_and_Find '):
            series_dir = dirParts[-4]
    except IndexError:
        series_dir = ''
    try:
        run_dir = dirParts[-2]
    except IndexError:
        run_dir = ''
    if match and not match in d:
        return

    series = {}
    for f in os.listdir(d):
        p = os.path.join(d, f)
        if os.path.isdir(p):
            if depth > 0:
                checkDir(p, r, match, depth-1)
        elif f == "results.csv":
            with open(p, "rt") as file:
                t = file.readlines()
            #  ,Label,Area,Mean,Min,Max,BX,BY,Width,Height
            # 1,Mark_and_Find 001:0001-0001-0369:WT_0TriDAP_0ML130_06080_t00_RAW_ch00,390818,161.834,66,210,10,81,1004,577
            slice_data = {}
            for l in t:
                if m := re.match(r".*:(\d+)-\d+-\d+:([^,]+),(\d+)", l):
                    slice = int(m[1])
                    label = m[2]
                    area = int(m[3])
                    val = 100.0 * area / 1024**2
                    slice_data[slice] = val + slice_data.get(slice, 0)
            for slice in range(1, max(slice_data.keys()) + 1):
                series[re.sub(r"_t\d+_", f"_t{slice - 1:02d}_", label, 1)] = slice_data.get(slice, 0)
        elif f.endswith(".mri.txt"):
            with open(p) as file:
                t = file.readlines()
            val = 0
            try:
                for l in t[1:]:
                    val += int(l.split("\t")[2].strip())
                key = re.sub(r"(?:\.(?:tiff?|png))?\.mri\.txt$", r"", f)
                series[key] = 100.0 * val / 1024**2
            except:
                print(f'Error reading file "{f}"')
    if len(series) > 0:
        settings_path = os.path.join(d, '..', 'settings.txt')
        settings = readSettings(settings_path)
        run = run_dir.split('_', 1)[1]
        sorted_func = sorted# if args.sort_simple else sorted_natural
        keys = sorted_func(series.keys())
        if args.verbose >= 2:
            print('\n'.join([f"    ~ {k}" for k in keys]))
        data = list([series[k] for k in keys])

        r.append({
            'name': series_dir,
            'mri_run': run,
            'data': data,
            'data_normalized': [d / max(data) if max(data) != 0 else 0 for d in data],
            'settings': settings
        })


parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('directory', type=str)#, nargs='+')
parser.add_argument('--all', '-a', action='store_true', help='show all mri tool runs, default: only newest')
parser.add_argument('--match', '-m', type=str, help='only show mri tool runs containing this string')
group = parser.add_mutually_exclusive_group()
group.add_argument('--depth', '-d', type=int, default=42, help='recursively search directory to a certain depth')
parser.add_argument('--timestep', '-t', type=float, default=0.25, help='imaging interval in (fractional) hours')
parser.add_argument('--verbose', '-v', action='count', default=0, help='print additional information, use twice to print all result file names during processing')
parser.add_argument('--sort-simple', '-s', action='store_true', help='do NOT sort result files naturally (convert all numerical parts to numbers, which are then compared (which fixes e.g. "a10x" vs "a101x")')
parser.add_argument('--disable-split-by-prefix', '-p', action='store_true', help='save all results to a single table instead of splitting into separate tables by prefix (e.g. "WT_siNOD1_4_1009" goes into a separate table "WT" as series "siNOD1_4_1009"')
args = parser.parse_args()

indir = args.directory

all_results = []
checkDir(indir, all_results, args.match, args.depth)

if not args.all:
    runs_by_name = {}
    for r in all_results:
        if not r['name'] in runs_by_name:
            runs_by_name[r['name']] = []
        runs_by_name[r['name']].append(r['mri_run'])
    
    print(f'### Found {len(all_results)} runs ###')
    if args.verbose >= 1:
        for name in runs_by_name:
            print(f"{name}:")
            for r in runs_by_name[name]:
                print(f" - {r}")
    
    del_runs = []
    for name in runs_by_name:
        runs = runs_by_name[name]
        if len(runs) > 1:
            runs.sort()
            for run in runs[:-1]:
                del_runs.append((name, run))
    all_results = [r for r in all_results if not (r['name'], r['mri_run']) in del_runs]

print(f"### Using {len(all_results)} runs ###")
for r in all_results:
    print(f" -> {r['name']} => {r['mri_run']}")

if not all_results:
    print("Found nothing :(")
else:
    summary_identifier = f'mritool-summary_{dt.now().strftime("%Y-%m-%d_%H-%M-%S")}'
    outdir = os.path.join(indir, summary_identifier)
    if not os.path.isdir(outdir):
        os.makedirs(outdir)

    sorted_func = sorted if args.sort_simple else sorted_natural
    all_results = sorted_func(all_results, lambda r: r['name'] + '#' + r['mri_run'])

    split_results = {None: all_results}
    if not args.disable_split_by_prefix:
        for _r in all_results:
            r = dict(_r) # create deep copy
            m = re.match(r"^(?:([^_\n]*[a-zA-Z][^_\n]*)_)?((?:([^_\n]*[a-zA-Z][^_\n]*(?:_[^_\n]+)?)_)(\d+))$", r['name'])
            # m = re.match(r"^(?:([^_\n]*[a-zA-Z][^_\n]*)_)?((?:([^_\n]*[a-zA-Z][^_\n]*(?:_\d+(?:\.\d+)?)?)_)(\d+))$", r['name'])
            prefix = m[1] or "" if m else ""
            name = m[2] or "" if m else ""
            r['name'] = name
            if len(prefix):
                if not prefix in split_results:
                    split_results[prefix] = []
                split_results[prefix].append(r)

    for result_prefix, results in split_results.items():
        for i in range(len(results)):
            results[i]['series_id'] = results[i]['name'] + ("" if not args.all else '_' + results[i]['mri_run'])

        if prefix is not None:
            print(f"### Filtered {len(results)} runs for prefix '{result_prefix}' ###")
            if args.verbose >= 1:
                for r in results:
                    print(f" -> {r['name']}")
        
        settings_merged = list(set().union(*[set(r['settings'].keys()) for r in results]))
        max_data_len = max([len(r['data']) for r in results])
        
        time_series = [x * args.timestep for x in range(0, max_data_len)]
        
        cols = []
        cols.append(
            ['name', 'mri_run']
            + settings_merged
            + ['id', '% of area']
            + [''] * (max_data_len - 1)
        )
        cols.append(
            [''] * 2
            + ['' for k in settings_merged]
            + ['Time [h]']
            + time_series
        )
        for r in results:
            cols.append([r['name'], r['mri_run']]
                + [(r['settings'][k] if k in r['settings'] else '') for k in settings_merged]
                + [r['series_id']]
                + r['data'] + [''] * (len(r['data']) - max_data_len)
            )

        safe_prefix = "".join(c if (c.isalnum() or c in "._- ") else "." for c in result_prefix or '')
        split_name = 'all' if result_prefix is None else f'prefix-{safe_prefix}'
        pout = os.path.join(outdir, f'{summary_identifier}_{split_name}.csv')
        print(f"Writing data for {split_name} to '{pout}'.")
        with open(pout, 'wt', encoding='UTF8', newline='') as f:
            writer = csv.writer(f)
            
            maxrows = max([len(c) for c in cols])
            for i in range(maxrows):
                row = []
                for c in cols:
                    row.append(c[i] if i < len(c) else '')
                writer.writerow(row)

        settings_path = os.path.join(outdir, f'{summary_identifier}_{split_name}_settings.txt')
        print(f"Writing thresholds for {split_name} to '{settings_path}'.")
        with open(settings_path, "wt", encoding='UTF8', newline='') as f:
            settings_pairs = []
            for r in results:
                settings_pairs.append((r['series_id'], str(r['settings']['threshold'])))
            max_id_length = max([len(x[0]) for x in settings_pairs])
            max_threshold_length = max([len(x[1]) for x in settings_pairs])

            series_head = 'Series'
            threshold_head = 'Threshold'
            maxlen = max_id_length + max_threshold_length
            id_chars = max(len(series_head), maxlen - len(threshold_head))
            f.write((f"%-{id_chars}s %s\n") % (series_head, threshold_head))
            for s in settings_pairs:
                f.write((f"%-{max_id_length}s %{max_threshold_length}s\n") % s)
    
    print("Done!")
