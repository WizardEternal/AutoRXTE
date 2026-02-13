# AutoRXTE Config - Quick Reference Card

## 🚨 CRITICAL: Energy Ranges

**Energy ranges are CHANNEL IDs (0-255), NOT keV!**

```yaml
# ✅ CORRECT
ranges:
  soft: "0-13"      # Channels 0-13 (~2-6 keV)
  
# ❌ WRONG  
ranges:
  soft: "2-6"       # This is channels 2-6, NOT 2-6 keV!
```

### Channel → Energy (Approximate)
| Channels | ~Energy | Name |
|----------|---------|------|
| 0-13 | 2-6 keV | Soft |
| 14-35 | 6-13 keV | Medium |
| 36-255 | 13-60 keV | Hard |

---

## Quick Start

1. **Copy config to your project:**
   ```bash
   cp autorxte_config.yaml my_config.yaml
   ```

2. **Edit parameters:**
   ```yaml
   color_analysis:
     ranges:
       soft: "0-10"
       medium: "11-30"
       hard: "31-255"
   ```

3. **Use in code:**
   ```python
   from autorxte.config import load_config
   load_config('my_config.yaml')
   
   extract_color_ranges(interactive=False)  # Uses your ranges!
   ```

---

## Most Common Parameters

### Time Bins
```yaml
extraction:
  time_bin: 0.004    # 4 ms (standard)
  time_bin: 0.001    # 1 ms (fast)
  time_bin: 0.000125 # 125 μs (QPOs)
```

### Energy Ranges (Channels!)
```yaml
color_analysis:
  ranges:
    soft: "0-13"
    medium: "14-35"
    hard: "36-255"
```

### GTI Filter
```yaml
filtering:
  filter_expression: "(ELV > 4) && (OFFSET < 0.1) && (NUM_PCU_ON > 0) && ..."
```

### PDS Settings
```yaml
pds:
  binning: -1        # Auto
  rebin: -1.03       # Geometric
  max_bins: 8192
```

### XSPEC Model
```yaml
xspec:
  default_model: diskbb_pexrav
  energy_range:
    min: 3.0         # keV (this IS in keV!)
    max: 30.0
```

---

## Usage Patterns

### 1. Default Config
```python
from autorxte.core import *

extract_all_events(interactive=False)  # Uses defaults
```

### 2. Custom Config
```python
from autorxte.config import load_config

load_config('my_config.yaml')
extract_all_events(interactive=False)  # Uses your config
```

### 3. Parameter Override
```python
extract_all_events(
    time_bin=0.001,  # Override config
    interactive=False
)
```

---

## Example Configs Provided

📁 **config_high_energy.yaml** - Hard X-ray focus
📁 **config_soft_thermal.yaml** - Soft/thermal states
📁 **config_qpo_analysis.yaml** - QPO detection

---

## Config Location Priority

1. `./autorxte_config.yaml` ← Your project (HIGHEST)
2. `~/.autorxte/config.yaml` ← Your home
3. Package default ← Fallback

---

## Common Customizations

### For Harder Sources
```yaml
color_analysis:
  ranges:
    low: "0-25"
    mid: "26-60"
    high: "61-255"
```

### For Softer Sources
```yaml
color_analysis:
  ranges:
    verysoft: "0-8"
    soft: "9-20"
    medium: "21-50"
```

### For QPO Search
```yaml
extraction:
  time_bin: 0.000125  # 125 μs

pds:
  max_bins: 16384
```

---

## Full Documentation

📖 **CONFIG_GUIDE.md** - Complete guide with all parameters
📖 **autorxte_config.yaml** - Default config with comments
📖 **examples/config_*.yaml** - Real-world examples

---

## Quick Tips

✅ Put config in project directory
✅ Document your changes with comments
✅ Test filter changes on one obs first
✅ Remember: channels NOT keV!
✅ Use 'auto' for workers
