# Scenario Expander Guide

`expander.py` expands logical scenario YAML plus parameter YAML into concrete core scenario YAML files.

## Scenario Types And CLI Selector

Scenario data is separated under `scenarios/<scenario_type>/`. The CLI selector
optionally starts with that scenario type:

```text
[<scenario_type>/]<feature_domain>/<functional>/<scenario_id>
[<scenario_type>/]<feature_domain>/<functional>
```

Supported scenario types currently used by this pipeline:

| Scenario type | Purpose | Selector example |
|---|---|---|
| `general_scenarios` | General ADAS functional test cases | `longitudinal/acc/acc_csc_001` |
| `ncap_scenarios` | Euro NCAP protocol-based cases | `ncap_scenarios/brake/aeb/aeb_cpna_001` |

When `<scenario_type>/` is omitted, the script resolves to
`general_scenarios` for backward compatibility.

```powershell
# General, implicit and explicit forms are equivalent
python expander\expander.py longitudinal/acc/acc_csc_001 --clean
python expander\expander.py general_scenarios/longitudinal/acc/acc_csc_001 --clean

# NCAP must specify its scenario type
python expander\expander.py ncap_scenarios/brake/aeb/aeb_cpna_001 --clean
python expander\expander.py ncap_scenarios/brake/aeb --clean
python expander\expander.py ncap_scenarios --all --clean
```

Files always remain inside the selected scenario type:

```text
scenarios/<scenario_type>/logical/<feature_domain>/<functional>/...
scenarios/<scenario_type>/parameters/<feature_domain>/<functional>/...
=> scenarios/<scenario_type>/core/<feature_domain>/<functional>/<scenario_id>/<case_id>.yaml
```

General scenarios use `<id>.yaml` paired with a converted parameter id, for
example `acc_csc_001.yaml` with `acc_par_001.yaml`. NCAP scenarios use:

```text
logical/<domain>/<function>/<id>_nsc.yaml
parameters/<domain>/<function>/<id>_par.yaml
=> core/<domain>/<function>/<id>/<id>_<case>.yaml
```

## 1. Required Metadata

Each logical YAML must define these keys:

```yaml
scenario_id: acc_csc_001
functional: ACC
feature_domain: Longitudinal
```

`expander.py` uses `functional` and `feature_domain` as the source of truth for output folders.

Supported `feature_domain` values currently map like this:

```text
Longitudinal -> longitudinal_feature
Lateral      -> lateral_feature
Parking      -> parking_feature
Brake        -> brake_feature
```

The parameter file is resolved from the same domain/function folder. The scenario id is converted from `csc` to `par`:

```text
acc_csc_001 -> acc_par_001
```

## 2. Run From This Folder

Open a terminal at:

```powershell
cd C:\Self_Improvement\FA_VnV\Test_assets_v1.4\expander
```

Then run commands with:

```powershell
python expander.py <selector>
```

You can also run from repo root:

```powershell
python expander\expander.py <selector>
```

## 3. Selector Format

Use this selector format. The leading scenario type is required for any set
other than `general_scenarios`:

```text
[<scenario_type>/]<feature_domain>/<functional>/<scenario_id>
```

Examples:

```text
longitudinal/acc/acc_csc_001
ncap_scenarios/brake/aeb/aeb_cpna_001
```

The selector is case-insensitive for domain and functional names:

```powershell
python expander.py longitudinal/acc/acc_csc_001
python expander.py Longitudinal/ACC/acc_csc_001
```

The two general commands resolve to:

```text
scenarios/general_scenarios/logical/longitudinal_feature/ACC/acc_csc_001.yaml
```

## 4. Generate One Scenario

Use this when you want to expand one logical scenario.

```powershell
python expander.py longitudinal/acc/acc_csc_001
```

Expected output:

```text
scenarios/general_scenarios/core/longitudinal_feature/ACC/acc_csc_001/
```

The number of generated YAML files depends on the parameter combinations and constraints in:

```text
scenarios/general_scenarios/parameters/longitudinal_feature/ACC/acc_par_001.yaml
```

## 5. Generate One Scenario With Clean

Use `--clean` when you want to remove the old output folder before regenerating.

```powershell
python expander.py longitudinal/acc/acc_csc_001 --clean
```

What `--clean` does:

1. Renames the old output folder to a temporary trash folder.
2. Deletes that trash folder.
3. Generates a fresh output folder.

Use this when parameters changed and you want to avoid stale old case files.

## 6. Generate Multiple Specific Scenarios

Pass multiple selectors in one command:

```powershell
python expander.py longitudinal/acc/acc_csc_001 longitudinal/acc/acc_csc_002 longitudinal/acc/acc_csc_003
```

With clean:

```powershell
python expander.py longitudinal/acc/acc_csc_001 longitudinal/acc/acc_csc_002 --clean
```

## 7. Generate A Range

Use a selector prefix plus `--from` and `--to`.

```powershell
python expander.py longitudinal/acc/acc_csc --from 1 --to 22
```

This expands:

```text
acc_csc_001
acc_csc_002
...
acc_csc_022
```

With clean:

```powershell
python expander.py longitudinal/acc/acc_csc --from 1 --to 22 --clean
```

Rules:

1. `--from` and `--to` must be used together.
2. Range mode accepts exactly one selector prefix.
3. Missing logical or parameter files are skipped and printed as `[SKIP]`.

## 8. Generate A Whole Functional Folder

Use only `<feature_domain>/<functional>`:

```powershell
python expander.py longitudinal/acc
```

This expands every `.yaml` file in:

```text
scenarios/general_scenarios/logical/longitudinal_feature/ACC/
```

With clean:

```powershell
python expander.py longitudinal/acc --clean
```

## 9. Generate Everything

Use `--all` to expand every logical YAML under `scenarios/general_scenarios/logical/`.

```powershell
python expander.py --all
```

With clean:

```powershell
python expander.py --all --clean
```

Use this carefully because it may regenerate many folders.

To expand all files in another scenario type, pass that type before `--all`:

```powershell
python expander.py ncap_scenarios --all --clean
```

## 10. Common Errors

`File not found: ... logical ...`

The selector does not match a logical YAML file. Check this path:

```text
scenarios/general_scenarios/logical/<feature_domain>/<functional>/<scenario_id>.yaml
```

`File not found: ... parameters ...`

The parameter YAML is missing. For `acc_csc_001`, the expected parameter file is:

```text
scenarios/general_scenarios/parameters/longitudinal_feature/ACC/acc_par_001.yaml
```

`Logical YAML ... must define 'functional' and 'feature_domain'`

Add the required metadata to the logical YAML:

```yaml
functional: ACC
feature_domain: Longitudinal
```

## 11. Recommended Workflow

1. Create or update the logical YAML.
2. Create or update the matching parameter YAML.
3. Run one scenario first:

```powershell
python expander.py longitudinal/acc/acc_csc_001 --clean
```

4. Inspect the generated core YAML folder.
5. If the output is correct, run a range or full functional folder.

For NCAP, apply the same workflow with the scenario-type prefix:

```powershell
python expander.py ncap_scenarios/brake/aeb/aeb_cpna_001 --clean
```
