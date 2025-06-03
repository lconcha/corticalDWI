#!/usr/bin/env python
import numpy as np
import argparse
import warnings

def get_mean_std(f_values_txt, f_vlaues_out):
    """
    Calculate mean and standard deviation of values in a text file.
    The file is expected to have whitespace-delimited values, with no headers.
    """
    
    # Load data (assuming whitespace-delimited, no headers, -1 for NaN)
    print(f"[INFO] Loading data from {f_values_txt}")
    data = np.loadtxt(f_values_txt)  # For headers: add `skiprows=1`
    nSt     = data.shape[0]  # Number of streamlines
    print(f"[INFO] Data shape: {data.shape}")
    # Replace -1 values for NaN
    data = np.where(data == -1, np.nan, data)

    # Calculate mean and std dev

    # Suppress the RuntimeWarning because of NaN values
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        means = np.nanmean(data, axis=0)
        stds = np.nanstd(data, axis=0, ddof=1)  # ddof=1 for sample stddev

    # Write to a file
    print(f"[INFO] Writing results to {f_vlaues_out}")
    with open(f_vlaues_out, 'w') as f:
        f.write(f"# {f_values_txt}\n")
        f.write(f"# nStreamlines: {nSt}\n")
        f.write("# Mean,Standard Deviation\n")
        for col in range(len(means)):
            f.write(f"{means[col]:.6f},{stds[col]:.6f}\n")
    print("[INFO] Done.")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate mean and std dev from a text file of values.")
    parser.add_argument("f_values_txt", type=str, help="Path to the input text file with values.")
    parser.add_argument("f_values_out", type=str, help="Path to the output text file for results.")
    args = parser.parse_args()

    # Set the file path from the argument
    f_values_txt = args.f_values_txt
    f_values_out = args.f_values_out

    # Call the function to compute mean and std
    get_mean_std(f_values_txt,f_values_out)

