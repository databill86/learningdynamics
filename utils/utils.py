import argparse
import os
import re
import numpy as np
import tensorflow as tf

from graph_nets import utils_tf

from utils.io import get_all_experiment_image_data_from_dir, get_experiment_image_data_from_dir, save_image_data_to_disk, create_dir


def get_args():
    argparser = argparse.ArgumentParser(description=__doc__)
    argparser.add_argument('-c', '--config', metavar='C', default='None', help='The Configuration file')

    argparser.add_argument('-n_epochs', '--n_epochs', default=None, help='overwrites the n_epoch specified in the configuration file', type=int)
    argparser.add_argument('-mode', '--mode', default=None, help='overwrites the mode specified in the configuration file')
    argparser.add_argument('-tfrecords_dir', '--tfrecords_dir', default=None, help='overwrites the tfrecords dir specified in the configuration file')

    argparser.add_argument('-old_tfrecords', '--old_tfrecords', default=False, action="store_true", help='overwrites the mode specified in the configuration file')
    argparser.add_argument('-normalize_data', '--normalize_data', default=True, action="store_false", help='indicates whether training and testing data should be normalized to cover values of range (0,1)')

    args, _ = argparser.parse_known_args()
    return args


def chunks(l, n):
  """Yield successive n-sized chunks from l.
  Used to create n sublists from a list l"""
  for i in range(0, len(l), n):
    yield l[i:i + n]


def natural_keys(text):
    '''
    alist.sort(key=natural_keys) sorts in human order
    http://nedbatchelder.com/blog/200712/human_sorting.html
    (See Toothy's implementation in the comments)
    float regex comes from https://stackoverflow.com/a/12643073/190597
    '''
    return [ atof(c) for c in re.split(r'[+-]?([0-9]+(?:[.][0-9]*)?|[.][0-9]+)', text) ]

def atof(text):
    try:
        retval = float(text)
    except ValueError:
        retval = text
    return retval


def get_number_of_total_samples(tf_records_filenames, options=None):
    c = 0
    for fn in tf_records_filenames:
        for _ in tf.python_io.tf_record_iterator(fn, options=options):
            c += 1
    return c

def make_all_runnable_in_session(*args):
  """Lets an iterable of TF graphs be output from a session as NP graphs."""
  return [utils_tf.make_runnable_in_session(a) for a in args]


def get_images_from_gn_output(outputs, depth=True, segmentation_only=False):
    images_rgb = []
    images_seg = []
    images_depth = []

    if segmentation_only:
        img_type = "seg"
    else:
        img_type = "all"

    n_objects = np.shape(outputs[0][0])[0]
    img_shape = get_correct_image_shape(config=None, n_leading_Nones=0, get_type=img_type, depth_data_provided=depth)

    for n in range(n_objects):
        rgb = []
        seg = []
        depth_lst = []
        for data_t in outputs:
            image = data_t.nodes[n][:-6-19200].reshape(img_shape)  # always get the n node features without vel+pos
            if segmentation_only:
                seg.append(np.expand_dims(image[:, :, 0], axis=2))
            else:
                rgb.append(image[:, :, :3])
                seg.append(np.expand_dims(image[:, :, 3], axis=2))
                if depth:
                    depth_lst.append(image[:, :, -3:])
        if segmentation_only:
            images_seg.append(np.stack(seg))
        else:
            images_rgb.append(np.stack(rgb))
            images_seg.append(np.stack(seg))
            if depth:
                images_depth.append(np.stack(depth_lst))
    # todo: possibly expand_dims before stacking since (exp_length, w, h, c) might become (w,h,c) if exp_length = 1
    return images_rgb, images_seg, images_depth


def get_latent_from_gn_output(outputs):
    n_objects = np.shape(outputs[0][0])[0]
    velocities = []
    positions = []
    # todo: implement gripperpos

    for n in range(n_objects):
        vel = []
        pos = []
        for data_t in outputs:
            obj_vel = data_t[0][n][-6:-3]
            obj_pos = data_t[0][n][-3:]
            pos.append(obj_pos)
            vel.append(obj_vel)
        velocities.append(vel)
        positions.append(pos)
    return positions, velocities


def get_pos_ndarray_from_output(output_for_summary):
    """ returns a position vector from a single step output, example shape: (exp_length,n_objects,3) for 3 = x,y,z dimension"""
    n_objects = np.shape(output_for_summary[0][0][0])[0]
    pos_lst = []
    for data_t in output_for_summary[0]:
        pos_t = []
        for n in range(n_objects):
            pos_object = data_t[0][n][-3:]
            pos_t.append(pos_object)
        pos_lst.append(np.stack(pos_t))

    return pos_lst


def get_correct_image_shape(config, n_leading_Nones=0, get_type="rgb", depth_data_provided = True):
    """ returns the correct shape (e.g. (120,160,7) ) according to the settings set in the configuration file """
    assert get_type in ['seg', 'depth', 'rgb', 'all']

    img_shape = None
    if config is None:
        depth = depth_data_provided
    else:
        depth = config.depth_data_provided

    if get_type is 'seg':
        img_shape = (120, 160, 1)
    elif get_type is 'depth' or get_type is 'rgb':
        img_shape = (120, 160, 3)
    elif get_type is 'all':
        if depth:
            img_shape = (120, 160, 7)
        else:
            img_shape = (120, 160, 4)

    for _ in range(n_leading_Nones):
        img_shape = (None, *img_shape)

    return img_shape


def check_exp_folder_exists_and_create(features, features_index, prefix, dir_name, cur_batch_it):
    exp_id = features[features_index]['experiment_id']
    if dir_name is not None:
        dir_path, _ = create_dir(os.path.join("../experiments", prefix), dir_name)
        dir_path, exists = create_dir(dir_path, "summary_images_batch_{}_exp_id_{}".format(cur_batch_it, exp_id))
        if exists:
            print("skipping export for exp_id: {} (directory already exists)".format(exp_id))
            return False
    else:
        dir_path = create_dir(os.path.join("../experiments", prefix), "summary_images_batch_{}_exp_id_{}".format(cur_batch_it, exp_id))
    return dir_path



def get_var_list_to_restore_by_name(var_name=None):
  """Choose which vars to restore, ignore vars by setting --checkpoint_exclude_scopes """
  slim = tf.contrib.slim
  FLAGS_checkpoint_exclude_scopes = None
  FLAGS_checkpoint_include_scopes = None  # 'resnet_v1_50'

  variables_to_restore = []
  if FLAGS_checkpoint_exclude_scopes is not None:
    exclusions = [scope.strip()
                  for scope in FLAGS_checkpoint_exclude_scopes.split(',')]

    # build restore list
    for var in tf.model_variables():
      for exclusion in exclusions:
        if var.name.startswith(exclusion):
          break
      else:
        variables_to_restore.append(var)
  else:
    variables_to_restore = tf.model_variables()

  variables_to_restore_final = []
  if var_name is not None:
      includes = [
              scope.strip()
              for scope in var_name.split(',')
              ]
      for var in variables_to_restore:
          for include in includes:
              if var.name.startswith(include):
                  variables_to_restore_final.append(var)
                  break
  else:
      variables_to_restore_final = variables_to_restore

  return variables_to_restore_final


def extract_input_and_output(outputs, targets, shape=None):
    ground_truth = []
    predictions = []
    if shape is None:
        shape = [-1, 120, 160]

    target_shape = [-1, 120, 160, 7]

    assert len(outputs) == len(targets), "outputs and target lists are not equally long"

    for output, target in zip(outputs, targets):
        output = output[0]  # first idx is the actual list, scnd is the batch index
        target = target[0]
        seg_img_experiment = []
        gt_seg_img_experiment = []
        for graph_output, graph_target in zip(output, target):
            seg_img = np.reshape(graph_output.nodes[:, :-6-19200], shape)  # shape (n_nodes, 120,160,2)
            seg_img_experiment.append(seg_img)


            gt_seg_img = np.reshape(graph_target.nodes[:, :-6], target_shape)  # actually has shape (n_nodes, 134406)
            gt_seg_img = gt_seg_img[:,:,:,3]
            gt_seg_img_experiment.append(gt_seg_img)
        predictions.append(seg_img_experiment)
        ground_truth.append(gt_seg_img_experiment)

    assert np.shape(ground_truth) == np.shape(predictions), "resulting prediction and ground truth list have not the same shape"

    return predictions, ground_truth

if __name__ == '__main__':
    source_path = "../data/source"
    exp_number = 5
    dest_path = os.path.join(source_path, str(exp_number))

    image_data = get_experiment_image_data_from_dir(source_path=source_path, experiment_id=exp_number, data_type="seg", as_dict=False)
    save_image_data_to_disk(image_data, dest_path, img_type="rgb")
    all_image_data = get_all_experiment_image_data_from_dir(source_path, data_type=["rgb", "seg"])

