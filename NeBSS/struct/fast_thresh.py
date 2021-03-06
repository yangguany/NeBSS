from map_maker import MapMaker
import colormaps
import nipype.interfaces.fsl as fsl
import fnmatch
import shutil
import os
import sys
import subprocess
from os import path
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
from res.misc import get_albert_labels, get_albert_colors


def check_for_fast(fast_dir):
    pve_4 = [n for n in fnmatch.filter(os.listdir(fast_dir),
                                       "*pve_3.nii.gz")
             if os.path.isfile(os.path.join(fast_dir, n))]
    if pve_4:
        return True
    else:
        return False


def get_file_name(seg_dir, pattern):
    bias_corrected = [n for n in fnmatch.filter(os.listdir(seg_dir),
                                                pattern)
                      if os.path.isfile(os.path.join(seg_dir, n))]
    return bias_corrected[0]


def run_fast(outputs_dir, in_file, contrast):
    """
    Deletes old Fast outputs and re-runs Fast in the
    old directory.
    Running with 4 classes
    Generally, for a neonatal T2:
        class 0 : CSF/hyperintense WM
        class 1 : WM
        class 2 : GM
        class 3 : Extra-axial CSF/Noise
    """
    fast_dir = os.path.join(outputs_dir, "Fast_PVE")
    [os.remove(os.path.join(fast_dir, n)) for n in os.listdir(fast_dir)]
    shutil.copy2(os.path.join(outputs_dir, "T2_Bias_Corrected", in_file),
                 fast_dir)
    cp_file = os.path.join(fast_dir, in_file)
    if contrast == "T2":
        img_type = 2
    elif contrast == "T1":
        img_type = 1
    os.chdir(fast_dir)
    FastSeg = fsl.FAST()
    FastSeg.inputs.img_type = img_type
    FastSeg.inputs.number_classes = 4
    FastSeg.inputs.output_biascorrected = False
    FastSeg.inputs.in_files = cp_file
    FastSeg.run()


def thresh_albert_gm(outputs_dir):
    in_file = os.path.join(outputs_dir,
                           get_file_name(outputs_dir, "*Albert_WTA*"))
    mask_file = os.path.join(outputs_dir, "Fast_PVE", get_file_name(
        os.path.join(outputs_dir, "Fast_PVE"), "*pve_2*"))
    maths = fsl.MultiImageMaths()
    maths.inputs.in_file = in_file
    maths.inputs.op_string = "-mas %s "
    maths.inputs.operand_files = [mask_file]
    maths.inputs.out_file = os.path.join(outputs_dir, "Albert_GM.nii.gz")
    maths.cmdline
    maths.run()


def get_mask_vol(prob_map):
    """
    Nipype ImageStats does not have the -K pre-option yet
    Pre-option fslstats -k returns a separate volume for each
    value in the mask
    So we are using a subprocess call instead
    """

    volumes = subprocess.check_output(["fslstats", "-K",
                                      prob_map, prob_map,
                                       "-V"]).split(' ')[:-1]
    return [(volumes[i], volumes[i+1]) for i in range(0, len(volumes), 2)]


def output_mask_volumes(mask_vols, output_file):
    labels = get_albert_labels()
    with open(output_file, 'wb') as f:
        for label in range(len(labels)):
            # Some of the labels have commas in them, bad for csv!
            tag = str(labels[str(label+1)]).replace(',', ' ')
            f.write('{0},'.format(tag))
        f.write('\n')
        for label in range(len(labels)):
            f.write("{0},".format(mask_vols[label][1]))
        f.write('\n')


def create_image(outputs_dir, struct_t2, mask, savefile):
    discrete = colormaps.custom_discrete("albert", get_albert_colors())
    image = MapMaker(struct_t2)
    image.add_overlay(mask, 0.01, 'max', discrete, alpha=0.8)
    image.save_strip_center(savefile, 19)


def main(outputs_dir):
    fast_dir = os.path.join(outputs_dir, "Fast_PVE")
    struct_t2 = get_file_name(os.path.join(outputs_dir,
                                           "T2_Bias_Corrected"),
                              "*_Bias_Corrected*")
    output_mask = os.path.join(outputs_dir, 'Albert_GM.nii.gz')
    output_csv = os.path.join(outputs_dir, "Albert_GM_Volumes.csv")
    output_image = os.path.join(outputs_dir, "Albert_GM_Volumes.png")

    if not check_for_fast(fast_dir):
        print("Running FSL Fast on file {0}".format(os.path.join(
                                                    outputs_dir, struct_t2)))
        run_fast(outputs_dir, struct_t2, "T2")
    else:
        print("Found 4 FAST classes")

    print("Thresholding ALBERT output for {0}".format(outputs_dir))
    thresh_albert_gm(outputs_dir)
    output_mask_volumes(get_mask_vol(output_mask), output_csv)
    create_image(outputs_dir, os.path.join(outputs_dir,
                                           "T2_Bias_Corrected",
                                           struct_t2),
                 output_mask, output_image)


if __name__ == "__main__":

    try:
        outputs_dir = os.path.abspath(sys.argv[1])
        main(outputs_dir)

    except IndexError:
        print("Please give path to Outputs directory")
