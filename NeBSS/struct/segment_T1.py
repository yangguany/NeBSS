import nipype.interfaces.io as nio
import nipype.interfaces.fsl as fsl
import  ants_ext as ants
import nipype.pipeline.engine as pe
import nipype.interfaces.utility as util
import os,json, sys
import time
from nipype import config

def determine_path():
    """
    determines the local path of the module on the OS
    """
    try:
        root = __file__
        if os.path.islink(root):
            root = os.path.realpath(root)
        return os.path.dirname(os.path.abspath(root))
    except:
        print "No __file__ variable"
        print "Problem with installation?"
        sys.exit()


local_path = determine_path()
print "local path: "+local_path

atlas_config = os.path.abspath(local_path+'/../../template_config.json')
with open(atlas_config, 'r') as f:
    atlas_dirs = json.load(f)


config_file = os.environ['nebss_config']
with open(config_file, 'r') as f:
    cfg = json.load(f)

print(os.environ)
isTest = os.environ['nebss_test']

parent_dir = cfg['parent_dir']
pca = int(cfg['pca'])
pid = cfg['pid']

Atlas2 = atlas_dirs['NeonatalAtlas2_DIR']
ALBERT = atlas_dirs['ALBERT_DIR']

T1_Template =os.path.abspath(Atlas2 + 'template_T1.nii.gz')

tissuelist = ['brainstem.nii.gz', 'cerebellum.nii.gz',
              'cortex.nii.gz', 'csf.nii.gz', 'dgm.nii.gz',
              'wm.nii.gz', 'brainmask.nii.gz',
              'itcsf.nii.gz','ivcsf.nii.gz','stcsf.nii.gz']

TissueList = [os.path.abspath(Atlas2) +'/'+
               tissue for tissue in tissuelist]

config.set('execution','crashdump_dir',parent_dir)


cropT1 = pe.Node(interface=fsl.ExtractROI(), name = 'cropT1')
cropT1.inputs.x_min =  cfg['T1_crop_box'][0]
cropT1.inputs.x_size = cfg['T1_crop_box'][1] - cfg['T1_crop_box'][0]
cropT1.inputs.y_min =  cfg['T1_crop_box'][2]
cropT1.inputs.y_size = cfg['T1_crop_box'][3] - cfg['T1_crop_box'][2]
cropT1.inputs.z_min =  cfg['T1_crop_box'][4]
cropT1.inputs.z_size = cfg['T1_crop_box'][5] - cfg['T1_crop_box'][4]
cropT1.inputs.in_file = cfg['T1_struct']

reorientT1 = pe.Node(interface=fsl.Reorient2Std(), name = 'reorientT1')

betT1 = pe.Node(interface=fsl.BET(),name='betT1')
betT1.inputs.frac=0.2
#betT1.inputs.robust=True
#betT1.inputs.center = cfg['T1_center']


FastSeg = pe.Node(interface=fsl.FAST(), name = 'FastSeg')
#FastSeg.inputs.terminal_output = 'stream'
FastSeg.inputs.output_biascorrected = True
FastSeg.inputs.img_type = 1
FastSeg.inputs.number_classes = 4


get_T1_template= pe.Node(interface=fsl.ExtractROI(),
                         name = 'get_T1_template')
get_T1_template.inputs.t_size = 1
get_T1_template.inputs.in_file = T1_Template


T1linTemplate = pe.Node(interface=fsl.FLIRT(), name='T1linTemplate')
T1linTemplate.inputs.dof = 12
T1linTemplate.inputs.searchr_x = [-180, 180]
T1linTemplate.inputs.searchr_y = [-180, 180]
T1linTemplate.inputs.searchr_z = [-180, 180]


### REAL PARAMETERS
T1warpTemplate=pe.Node(interface=ants.ANTS(), name='T1warpTemplate')
T1warpTemplate.inputs.dimension=3
T1warpTemplate.inputs.metric=['CC',]
T1warpTemplate.inputs.metric_weight=[1.0,]
T1warpTemplate.inputs.radius=[10,]
T1warpTemplate.inputs.output_transform_prefix='ANTS_OUT'
T1warpTemplate.inputs.transformation_model='SyN'
T1warpTemplate.inputs.gradient_step_length=5
T1warpTemplate.inputs.number_of_time_steps=5
T1warpTemplate.inputs.delta_time=0.01
T1warpTemplate.inputs.regularization='Gauss'
T1warpTemplate.inputs.regularization_gradient_field_sigma=0
T1warpTemplate.inputs.regularization_deformation_field_sigma=3

if isTest:
	T1warpTemplate.inputs.number_of_iterations=[2,2,2,1] #test parameters
else:
	T1warpTemplate.inputs.number_of_iterations=[100,100,100,50]

T1warpTemplate.config = {'execution':
                         {'remove_unnuecessary_outputs' : False}
                         }

def agg_transforms(warp, affine):
    return [warp, affine]

def inv_agg_transforms(warp, affine):
    return [affine, warp]

T1_warp_to_standard=pe.Node(interface=ants.WarpImageMultiTransform(),
                               name='T1_warp_to_standard')


T1_warp_to_standard_agg = pe.Node(name='T1_warp_to_standard_agg',
                    interface = util.Function(input_names=['warp','affine'],
                                         output_names=['trans_series'],
                                         function = agg_transforms))


apply_T1_warp=pe.MapNode(interface=ants.WarpImageMultiTransform(),
                         name='apply_T1_warp',
                         iterfield=['input_image'])
apply_T1_warp.inputs.invert_affine = [1,]

apply_T1_warp_agg = pe.Node(name='apply_T1_warp_agg',
                    interface = util.Function(input_names=['warp','affine'],
                                         output_names=['trans_series'],
                                         function = inv_agg_transforms))

get_masks = pe.MapNode(interface=fsl.ExtractROI(), name = 'get_masks',
                              iterfield=['in_file'])
get_masks.inputs.t_size = 1
get_masks.inputs.in_file = TissueList


def get_index(PCA):
    if PCA >= 44:
        return 16
    elif PCA <= 28:
        return 0
    else:
        return PCA - 28

get_template_index = pe.Node(name='get_template_index',
                    interface = util.Function(input_names=['PCA'],
                                         output_names=['index'],
                                         function = get_index))
get_template_index.inputs.PCA = pca


albert_group = cfg['albert_group']
def get_albert_group(group,local_path,ALBERT):
    import os
    groups = {
        '<27':['06','09','15','17','18'],
        '27-30':['08','10','11','12','14','20'],
        '30-36':['07','13','16','19'],
        'Term':['01','02','03','04','05']
    }
    return [os.path.abspath(ALBERT +'volumes/{0}_T1_brain.nii.gz'.format(x))
                              for x in groups[group]]



get_albert_list= pe.Node(name='get_albert_list',
                    interface = util.Function(input_names=['group','local_path', 'ALBERT'],
                                         output_names=['albert_list'],
                                         function = get_albert_group))
get_albert_list.inputs.group = albert_group
get_albert_list.inputs.local_path = local_path
get_albert_list.inputs.ALBERT = ALBERT

def get_seg_list(group,local_path,ALBERT):
    import os
    groups = {
        '<27':['06','09','15','17','18'],
        '27-30':['08','10','11','12','14','20'],
        '30-36':['07','13','16','19'],
        'Term':['01','02','03','04','05']
    }
    return [os.path.abspath(ALBERT + 'segmentations/ALBERT_{0}_ISG_seg50.nii'.format(x))
                              for x in groups[group]]



get_albert_seg= pe.Node(name='get_albert_seg',
                    interface = util.Function(input_names=['group','local_path','ALBERT'],
                                         output_names=['seg_list'],
                                         function = get_seg_list))
get_albert_seg.inputs.group = albert_group
get_albert_seg.inputs.local_path = local_path
get_albert_seg.inputs.ALBERT = ALBERT


#### REAL PARAMETERS
albert_warp=pe.MapNode(interface=ants.ANTS(),
                       name='albert_warp',
                       iterfield=['moving_image'])
albert_warp.inputs.dimension=3
albert_warp.inputs.metric=['CC',]
albert_warp.inputs.metric_weight=[1.0,]
albert_warp.inputs.radius=[10,]
albert_warp.inputs.output_transform_prefix='ANTS_OUT'
albert_warp.inputs.transformation_model='SyN'
albert_warp.inputs.gradient_step_length=5
albert_warp.inputs.number_of_time_steps=5
albert_warp.inputs.delta_time=0.01
albert_warp.inputs.regularization='Gauss'
albert_warp.inputs.regularization_gradient_field_sigma=0
albert_warp.inputs.regularization_deformation_field_sigma=3

if isTest:
	albert_warp.inputs.number_of_iterations=[2,2,2,1] #test parameters
else:
	albert_warp.inputs.number_of_iterations=[100,100,100,50]

albert_warp.config = {'execution':
                         {'remove_unnuecessary_outputs' : False}
                         }


apply_albert_warp=pe.MapNode(interface=ants.WarpImageMultiTransform(),
                             name='apply_albert_warp',
                             iterfield=['input_image','transformation_series'])
apply_albert_warp.inputs.use_nearest = True
apply_albert_warp.synchronize = True

apply_albert_warp_agg = pe.MapNode(name='apply_albert_warp_agg',
                    interface = util.Function(input_names=['warp','affine'],
                                         output_names=['trans_series'],
                                         function = agg_transforms),
                                          iterfield=['warp','affine'])
apply_albert_warp_agg.synchronize = True


AlbertSeg = pe.Workflow(name='AlbertSeg')
AlbertSeg.base_dir = os.path.join(parent_dir,'/SegT1')
AlbertSeg.connect([
               (get_albert_list, albert_warp, [('albert_list','moving_image')]),
         (albert_warp, apply_albert_warp_agg, [('warp_transform', 'warp'),
                                               ('affine_transform', 'affine')]),
   (apply_albert_warp_agg, apply_albert_warp, [('trans_series','transformation_series')]),
          (get_albert_seg, apply_albert_warp, [('seg_list', 'input_image')])
])


datasink_dir = os.path.join(parent_dir,'SegT1/Outputs')
datasink = pe.Node(interface=nio.DataSink(), name='datasink')
datasink.inputs.base_directory = datasink_dir
datasink.inputs.substitutions = [('_apply_T1_warp', ''),
                                 ('_roi_reoriented_brain_restore_wimt', '_T1_StdSpace'),
                                 ('_roi_reoriented_brain_restore','_T2_Bias_Corrected'),
                                 ('_roi_reoriented_brain_pve', 'pve'),
                                 ('_roi_wimt', ''),
                                 ('_apply_albert_warp','')]



SegT1 = pe.Workflow(name='SegT1')
SegT1.base_dir = parent_dir
SegT1.connect([
                      (cropT1, reorientT1, [('roi_file', 'in_file')]),
                       (reorientT1, betT1, [('out_file', 'in_file')]),
                          (betT1, FastSeg, [('out_file', 'in_files')]),
     (get_template_index, get_T1_template, [('index', 't_min')]),
                 (FastSeg, T1warpTemplate, [('restored_image', 'moving_image')]),
         (get_T1_template, T1warpTemplate, [('roi_file', 'fixed_image')]),
           (get_template_index, get_masks, [('index', 't_min')]),
       (T1warpTemplate, apply_T1_warp_agg, [('inverse_warp_transform', 'warp'),
                                            ('affine_transform', 'affine')]),
        (apply_T1_warp_agg, apply_T1_warp, [('trans_series', 'transformation_series')]),
                (get_masks, apply_T1_warp, [('roi_file', 'input_image')]),
                  (FastSeg, apply_T1_warp, [('restored_image', 'reference_image')]),
                      (FastSeg, AlbertSeg, [('restored_image','albert_warp.fixed_image')]),
                      (FastSeg, AlbertSeg, [('restored_image',
                                                     'apply_albert_warp.reference_image')]),
            (FastSeg, T1_warp_to_standard, [('restored_image', 'input_image')]),
 (T1warpTemplate, T1_warp_to_standard_agg, [('warp_transform', 'warp'),
                                            ('affine_transform', 'affine')]),
(T1_warp_to_standard_agg,
                      T1_warp_to_standard, [('trans_series', 'transformation_series')]),
                (T1warpTemplate, datasink, [('warp_transform','T1WarpTemplate.@std_transform'),
                                            ('inverse_warp_transform','T1WarpTemplate.@std_inv_transform')]),
                     (AlbertSeg, datasink, [('albert_warp.warp_transform','T1WarpTemplate.@albert_transform'),
                                            ('albert_warp.inverse_warp_transform',
                                                            'T1WarpTemplate.@albert_inv_transform')]),
           (T1_warp_to_standard, datasink, [('output_image', 'T1_Standard_Space.@T1W')]),
                       (FastSeg, datasink, [('partial_volume_files', 'Fast_PVE.@FPVE')]),
                 (apply_T1_warp, datasink, [('output_image', 'T1_Tissue_Classes.@T1TC')]),
                       (FastSeg, datasink, [('restored_image',
                                                    'T1_Bias_Corrected.@T1B')]),
                     (AlbertSeg, datasink, [('apply_albert_warp.output_image',
                                                                'Reg_Alberts.@MA')])
                                ])

from nipype.interfaces.fsl import ImageStats,Merge
import colormaps
from map_maker import MapMaker
from nipy import load_image, save_image
from nipy.core.api import Image
import numpy as np

def get_volume(mask):
    """
    Fslstats -V returns volume [voxels mm3]
    Fslstats -M returns mean value of non-zero voxels
    Multiplying these gives the partial volume estimate
    """
    Volume = ImageStats(in_file = mask, op_string = '-V -M')
    Vout=Volume.run()
    outstat = Vout.outputs.out_stat
    return outstat[1] * outstat[2]

def output_volume(parent_dir, pid, con):
    mskdir = parent_dir+'/SegT1/Outputs/'+str(con)+'_Tissue_Classes/'
    bs_vol = get_volume(mskdir+'0/brainstem.nii.gz')
    cb_vol = get_volume(mskdir+'1/cerebellum.nii.gz')
    ctx_vol = get_volume(mskdir+'2/cortex.nii.gz')
    csf_vol = get_volume(mskdir+'3/csf.nii.gz')
    dgm_vol = get_volume(mskdir+'4/dgm.nii.gz')
    wm_vol = get_volume(mskdir+'5/wm.nii.gz')
    brain_vol = get_volume(mskdir+'6/brainmask.nii.gz')
    x_itcsf = get_volume(mskdir+'7/itcsf.nii.gz')
    x_ivcsf = get_volume(mskdir+'8/ivcsf.nii.gz')
    x_stcsf = get_volume(mskdir+'9/stcsf.nii.gz')

    return [con, bs_vol, cb_vol, ctx_vol,
            csf_vol, dgm_vol, wm_vol,brain_vol,
            x_itcsf, x_ivcsf, x_stcsf]



def merge_regs(out_dir, out_file):
    import subprocess, shlex
    folder_list = [out_dir+folder for folder in os.listdir(out_dir)]
    print folder_list
    file_list = [folder+'/'+(os.listdir(folder)[0])
                 for folder in folder_list]
    merger = Merge()
    merger.inputs.in_files = file_list
    merger.inputs.dimension = 't'
    merger.inputs.merged_file = out_file
    print merger.cmdline
    command = shlex.split(merger.cmdline)
    subprocess.call(command)



def get_mode(seg_stack, out_file):
    img = load_image(seg_stack)
    new_coord = img[:,:,:,0].coordmap
    data = img.get_data()
    mode = np.zeros(data.shape[:3])
    for i in xrange(data.shape[0]):
        for j in xrange(data.shape[1]):
            for k in xrange(data.shape[2]):
                u, indices = np.unique(data[i,j,k,:],
                                       return_inverse=True)
                voxel_mode = u[np.argmax(np.bincount(indices))]
                print "mode at {0},{1},{2} = {3}".format(i,j,k,voxel_mode)
                mode[i,j,k] = voxel_mode
    mode_image = Image(mode, new_coord)
    save_image(mode_image, out_file)
    return mode


def create_image(parent_dir, pid, savefile):
    sourcedir = parent_dir+'/SegT1/Outputs/'
    bg = sourcedir+'T1_Bias_Corrected/'+(os.listdir(sourcedir+'T1_Bias_Corrected/')[0])
    mskdir = sourcedir+'T1_Tissue_Classes/'
    image = MapMaker(bg)
    image.add_overlay(mskdir+'3/csf.nii.gz', 0.05, 1, colormaps.csf(), alpha = 0.7)
    image.add_overlay(mskdir+'2/cortex.nii.gz', 0.05, 1, colormaps.cortex(), alpha = 0.7)
    image.add_overlay(mskdir+'0/brainstem.nii.gz', 0.05, 1, colormaps.brainstem(), alpha = 0.7)
    image.add_overlay(mskdir+'1/cerebellum.nii.gz', 0.05, 1, colormaps.cerebellum(), alpha = 0.7)
    image.add_overlay(mskdir+'4/dgm.nii.gz', 0.05, 1, colormaps.dgm(), alpha = 0.7)
    image.add_overlay(mskdir+'5/wm.nii.gz', 0.05, 1, colormaps.wm(), alpha = 0.7)
    image.save_strip_center(savefile+'.png', 20)




start = time.time()
SegT1.write_graph()
SegT1.run()


pid = pid
print pid
T1Vols = output_volume(parent_dir, pid, 'T1')


with open(parent_dir+'/SegT1/Outputs/Metrics.csv', 'wb') as f:
    f.write('Contrast,Brainstem,Cerebellum, Cortex, CSF, DGM, WM, Brain, ITCSF, IVCSF, STCSF\n')
    f.write('{0},{1:.7},{2:.7},{3:.7},{4:.7},{5:.7},{6:.7},{7:.7},{8:.7},{9:.7},{10:.7}\n'.format(*T1Vols))

T1Save = cfg['parent_dir'] + '/SegT1/Outputs/'+pid+'_T1_Segmentation'
AlbertSave = cfg['parent_dir'] + '/SegT1/Outputs/'+pid+'_Albert_WTA'
AlbertFile = cfg['parent_dir'] + '/SegT1/Outputs/'+pid+'_Albert_Stack.nii.gz'
AlbertOutDir = cfg['parent_dir']+'/SegT1/Outputs/Reg_Alberts/'
print AlbertOutDir

merge_regs(AlbertOutDir, AlbertFile)
get_mode(AlbertFile, AlbertSave)
create_image(parent_dir, pid,T1Save)

finish = (time.time() - start) / 60

print 'Time taken: {0:.7} minutes'.format(finish)











