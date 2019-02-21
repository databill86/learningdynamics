import argparse
import os
import re
import numpy as np
import tensorflow as tf
import math

from graph_nets import utils_tf

from utils.io import get_all_experiment_image_data_from_dir, get_experiment_image_data_from_dir, save_image_data_to_disk, create_dir


def get_args():
    argparser = argparse.ArgumentParser(description=__doc__)
    argparser.add_argument('-c', '--config', metavar='C', default='None', help='The Configuration file')

    argparser.add_argument('-n_epochs', '--n_epochs', default=None, help='overwrites the n_epoch specified in the configuration file', type=int)
    argparser.add_argument('-mode', '--mode', default=None, help='overwrites the mode specified in the configuration file')
    argparser.add_argument('-tfrecords_dir', '--tfrecords_dir', default=None, help='overwrites the tfrecords dir specified in the configuration file')

    argparser.add_argument('-old_tfrecords', '--old_tfrecords', default=False, action="store_true", help='overwrites the mode specified in the configuration file')


    args, _ = argparser.parse_known_args()
    return args

def convert_batch_to_list(batch, fltr):
    """
    Args:
        batch:
        fltr: a list of words specifying the keys to keep in the list
    Returns:

    """
    assert type(batch) == dict
    data = []
    for batch_element in batch.values():
        sublist = []
        for i in batch_element.values():
            sublist.append([v for k, v in i.items() for i in fltr if i in k])
        data.append(sublist)
    return data

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


def convert_dict_to_list(dct):
    """ assumes a dict of subdicts of which each subdict only contains one key containing the desired data """
    lst = []
    for value in dct.values():
        if len(value) > 1:
            lst.append(list(value.values()))
        else:
            element = next(iter(value.values())) # get the first element, assuming the dicts contain only the desired data
            lst.append(element)
    return lst


def convert_dict_to_list_subdicts(dct, length):
    list_of_subdicts = []
    for i in range(length):
        batch_item_dict = {}
        for k, v in dct.items():
            batch_item_dict[k] = v[i]
        list_of_subdicts.append(batch_item_dict)
    return list_of_subdicts


def convert_list_of_dicts_to_list_by_concat(lst):
    """ concatenate all entries of the dicts into an ndarray and append them into a total list """
    total_list = []
    for dct in lst:
        sub_list = []
        for v in list(dct.values()):
            sub_list.append(v)
        sub_list = np.concatenate(sub_list)
        total_list.append(sub_list)
    return total_list

def convert_float_image_to_int16_legacy(float_image): #todo: remove wrong (65k vs 255) conversion when creating new tfrecords
    dt = float_image.dtype
    float_image = float_image.astype(dt) / float_image.max()
    float_image = 255 * float_image
    return float_image.astype(np.int16)


def get_number_of_total_samples(tf_records_filenames, options=None):
    c = 0
    for fn in tf_records_filenames:
        for _ in tf.python_io.tf_record_iterator(fn, options=options):
            c += 1
    return c

def make_all_runnable_in_session(*args):
  """Lets an iterable of TF graphs be output from a session as NP graphs."""
  return [utils_tf.make_runnable_in_session(a) for a in args]


def get_images_from_gn_output(outputs, depth=True):
    images_rgb = []
    images_seg = []
    images_depth = []

    n_objects = np.shape(outputs[0][0])[0]
    img_shape = get_correct_image_shape(config=None, n_leading_Nones=0, get_type='all', depth_data_provided=depth)

    for n in range(n_objects):
        rgb = []
        seg = []
        depth_lst = []
        for data_t in outputs:
            image = data_t[0][n][:-6].reshape(img_shape)  # always get the n node features without pos+vel
            rgb.append(image[:, :, :3])
            seg.append(np.expand_dims(image[:, :, 3], axis=2))
            if depth:
                depth_lst.append(image[:, :, -3:])
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
            obj_vel = data_t[0][n][-3:]
            obj_pos = data_t[0][n][-6:-3]
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


def is_square(integer):
    root = math.sqrt(integer)
    if int(root + 0.5) ** 2 == integer:
        return True
    else:
        return False


def check_power(N, k):
    if N == k:
        return True
    try:
        return N == k**int(round(math.log(N, k)))
    except Exception:
        return False

def check_exp_folder_exists_and_create(features, features_index, prefix, dir_name, cur_batch_it):
    exp_id = features[features_index]['experiment_id']
    if dir_name is not None:
        dir_path, _ = create_dir(os.path.join("../experiments", prefix), dir_name)
        dir_path, exists = create_dir(dir_path, "summary_images_batch_{}_exp_id_{}".format(cur_batch_it, exp_id))
        if exists:
            print("skipping image export for exp_id: {} (directory already exists)".format(exp_id))
            return None
    else:
        dir_path = create_dir(os.path.join("../experiments", prefix), "summary_images_batch_{}_exp_id_{}".format(cur_batch_it, exp_id))
    return dir_path


def normalize_list(lst):
    """ normalizes a list of 3-dim ndarrays x s.t. all x's contain values in (0,1) """
    x_min = 0.344
    y_min = -0.256
    z_min = -0.149
    x_max = 0.856
    y_max = 0.256
    z_max = -0.0307

    x_norm = lambda x: (x - x_min) / (x_max - x_min)
    y_norm = lambda y: (y - y_min) / (y_max - y_min)
    z_norm = lambda z: (z - z_min) / (z_max - z_min)

    return [np.asarray([x_norm(coords[0]), y_norm(coords[1]), z_norm(coords[2])]) for coords in lst]


def normalize_df(df):
    """ normalizes an entire pandas dataframe in which each cell c contains a 3-dim ndarray s.t. c only contains values in (0,1) """
    x_min = 0.344
    y_min = -0.256
    z_min = -0.149
    x_max = 0.856
    y_max = 0.256
    z_max = -0.0307

    x_norm = lambda x: (x - x_min) / (x_max - x_min)
    y_norm = lambda y: (y - y_min) / (y_max - y_min)
    z_norm = lambda z: (z - z_min) / (z_max - z_min)

    def _normalize_column(column):
        for index, row_value in column.items():
            column[index] = np.asarray([x_norm(row_value[0]), y_norm(row_value[1]), z_norm(row_value[2])])
        return column

    return df.apply(_normalize_column, axis=1)


def normalize_df_column(df, column_name):
    """ normalizes an entire pandas column (series) in which each row r contains a 3-dim ndarray s.t. all values of r in range (0,1) """
    x_min = 0.344
    y_min = -0.256
    z_min = -0.149
    x_max = 0.856
    y_max = 0.256
    z_max = -0.0307

    x_norm = lambda x: (x - x_min) / (x_max - x_min)
    y_norm = lambda y: (y - y_min) / (y_max - y_min)
    z_norm = lambda z: (z - z_min) / (z_max - z_min)

    def _normalize_row(row):
        return np.asarray([x_norm(row[0]), y_norm(row[1]), z_norm(row[2])])

    return df[column_name].apply(_normalize_row)





if __name__ == '__main__':
    source_path = "../data/source"
    exp_number = 5
    dest_path = os.path.join(source_path, str(exp_number))

    image_data = get_experiment_image_data_from_dir(source_path=source_path, experiment_id=exp_number, data_type="seg", as_dict=False)
    save_image_data_to_disk(image_data, dest_path, img_type="rgb")
    all_image_data = get_all_experiment_image_data_from_dir(source_path, data_type=["rgb", "seg"])

