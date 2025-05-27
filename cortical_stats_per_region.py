#!/usr/bin/env python
import numpy as np

f_values_txt = "csd_fixels_singletissue/lh_fsLR-32k_afd-par.txt"
f_indices      = "split/lh_fsLR-32k_laplace-wm-streamlines_dwispace_11174_indices.txt"

# Load data (assuming whitespace-delimited, no headers)
data = np.loadtxt(f_values_txt)  # For headers: add `skiprows=1`
ix   = np.loadtxt(f_indices)

print(data.shape)

indices = ix > 0
nSt     = indices.sum()

# Calculate mean and std dev
means = np.mean(data[indices,], axis=0)
stds = np.std(data[indices,], axis=0, ddof=1)  # ddof=1 for sample stddev

print(f"# {f_values_txt}")
print(f"# nStreamlines: {nSt}")
print("# mean,std")

# Print results
for col in range(data.shape[1]):
    print(f"{means[col]:.4f},{stds[col]:.4f}")