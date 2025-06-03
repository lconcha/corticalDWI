#!/usr/bin/env python3
# -*- coding: utf-8 -*


import nibabel as nib
import numpy as np
import argparse



def truncate_streamline(streamline, max_length):
    """
    Truncates a streamline to the specified maximum length.
    """
    if len(streamline) < 2:
        return streamline

    segment_lengths = np.linalg.norm(streamline[1:] - streamline[:-1], axis=1)
    cumulative_lengths = np.insert(np.cumsum(segment_lengths), 0, 0.0)

    if cumulative_lengths[-1] <= max_length:
        return streamline

    # Find the index where the cumulative length exceeds max_length
    cutoff_idx = np.searchsorted(cumulative_lengths, max_length)
    return streamline[:cutoff_idx + 1]




def _resample_single_streamline(streamline, step_size):
    """
    Resamples a single streamline to have points separated by 'step_size'
    using linear interpolation (NumPy only).
    """
    if len(streamline) < 2:
        return streamline

    segment_lengths = np.linalg.norm(streamline[1:] - streamline[:-1], axis=1)
    cumulative_lengths = np.insert(np.cumsum(segment_lengths), 0, 0.0)
    total_length = cumulative_lengths[-1]

    if total_length < step_size and len(streamline) <= 2:
        return streamline

    new_depths = np.arange(0.0, total_length + 1e-9, step_size)
    if len(new_depths) == 0:
        return np.array([streamline[0]])

    resampled_x = np.interp(new_depths, cumulative_lengths, streamline[:, 0])
    resampled_y = np.interp(new_depths, cumulative_lengths, streamline[:, 1])
    resampled_z = np.interp(new_depths, cumulative_lengths, streamline[:, 2])

    return np.vstack((resampled_x, resampled_y, resampled_z)).T

def resample_tck_file(f_tck_in, f_tck_out, step_size,max_length=None):
    """
    Loads a .tck file, resamples all its streamlines, and saves to a new .tck.
    """
    print(f"Loading {f_tck_in}...")
    try:
        tck = nib.streamlines.load(f_tck_in)
    except FileNotFoundError:
        print(f"Error: Input file '{f_tck_in}' not found.")
        return
    except Exception as e:
        print(f"Error loading {f_tck_in}: {e}")
        return

    original_streamlines = tck.streamlines
    nStreamlines = len(original_streamlines)
    print(f"Loaded {nStreamlines} streamlines from {f_tck_in}.")
    resampled_streamlines_data = []

    print(f"Resampling streamlines to step size {step_size}...")
    if max_length is not None:
        print(f"Truncating streamlines longer than {max_length} mm.")

    for streamline in original_streamlines:
        if streamline.ndim == 1:
            print("Warning: Detected a 1D streamline, reshaping to 2D.")
            streamline = streamline.reshape(1, -1)
        
        # First resample at high resolution in case we need to truncate later
        step_size_hires = step_size / 10.0  # High-resolution step size
        resampled_sl = _resample_single_streamline(streamline, step_size_hires)
        
        # Optionally truncate the streamline if a maximum length is specified
        if max_length is not None:
            resampled_sl = truncate_streamline(resampled_sl, max_length)

        # Resample to the final step size
        resampled_sl = _resample_single_streamline(resampled_sl, step_size)

        resampled_streamlines_data.append(resampled_sl)

    # In older nibabel versions, 'nibabel.streamlines.Streamlines' might not exist
    # Try using 'nibabel.streamlines.ArraySequence', which is a common internal
    # representation that should have the necessary methods.
    try:
        StreamlinesClass = nib.streamlines.Streamlines # Try the preferred modern way first
    except AttributeError:
        # Fallback for older versions if Streamlines is not directly exposed
        StreamlinesClass = nib.streamlines.ArraySequence # This should exist if load() works

    streamlines_for_tckfile = StreamlinesClass(resampled_streamlines_data)

    
    # Create a Tractogram with the correct affine
    tractogram = nib.streamlines.tractogram.Tractogram(streamlines_for_tckfile, affine_to_rasmm=tck.tractogram.affine_to_rasmm)


   
    print(f"Saving resampled TCK to {f_tck_out}...")
    try:
        # Use the original header for consistency      
        #header = dict(tck.header) # Make a mutable copy
        #header['comments'] = [f"Resampled with step size {step_size} mm"]
        if max_length is not None:
            header['comments'].append(f"Truncated streamlines longer than {max_length} mm")
        nib.streamlines.save(tractogram, f_tck_out, header=tck.header)
        print("Done.")
    except Exception as e:
        print(f"Error saving output file '{f_tck_out}': {e}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Load a .tck file, resample its streamlines to a specified step size, and save the result."
    )

    parser.add_argument(
        "input_tck",
        type=str,
        help="Path to the input .tck file."
    )
    parser.add_argument(
        "output_tck",
        type=str,
        help="Path for the output resampled .tck file."
    )
    parser.add_argument(
        "--step_size",
        type=float,
        default=0.5,
        help="The desired Euclidean distance (in mm) between consecutive points after resampling. Default: 0.5."
    )
    parser.add_argument(
    "--max_length",
    type=float,
    default=None,
    help="Maximum length (in mm) for each streamline. Streamlines longer than this will be truncated."
    )


    args = parser.parse_args()



resample_tck_file(
    f_tck_in=args.input_tck,
    f_tck_out=args.output_tck,
    step_size=args.step_size,
    max_length=args.max_length
)
