import numpy as np
import tensorflow as tf
import tflearn
import sys
import os
from utils.utils import get_var_list_to_restore_by_name
from base.base_model import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(BASE_DIR,'../')
sys.path.append(BASE_DIR)

model_dirs = os.path.join(os.path.dirname(os.path.abspath(__file__)),'./.')

class baseline_auto_predictor_extended_multistep(BaseModel):
    def __init__(self, config, name="baseline_auto_predictor_extended_multistep"):
        super(baseline_auto_predictor_extended_multistep, self).__init__(self)
        self.config = config

        # init the batch counter
        self.init_batch_step()

        self.optimizer = tf.train.AdamOptimizer(self.config.learning_rate)

    def encoder(self, in_rgbsegxyz, is_training):
        x = in_rgbsegxyz
        """ Layer 1 """
        x = tflearn.layers.conv.conv_2d(x, 128, (3, 3), strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', scope="conv1_1")
        x = tflearn.layers.normalization.batch_normalization(x)

        """ Layer 2 """
        x = tflearn.layers.conv.conv_2d(x, 128, (3, 3), strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', scope="conv1_2")
        x = tflearn.layers.normalization.batch_normalization(x)
        x = tflearn.layers.conv.max_pool_2d(x, 2, 2)

        """ Layer 3 """
        x = tflearn.layers.conv.conv_2d(x, 256, (3, 3), strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', scope="conv1_3")
        x = tflearn.layers.normalization.batch_normalization(x)

        """ Layer 4 """
        x = tflearn.layers.conv.conv_2d(x, 256, (3, 3), strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', scope="conv1_4")
        x = tflearn.layers.normalization.batch_normalization(x)
        x = tflearn.layers.conv.max_pool_2d(x, 2, 2)

        """ Layer 5 """
        x = tflearn.layers.conv.conv_2d(x, 256, (3, 3), strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', scope="conv1_5")
        x = tflearn.layers.normalization.batch_normalization(x)

        """ Layer 6 """
        x = tflearn.layers.conv.conv_2d(x, 256, (3, 3), strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', scope="conv1_6")
        x = tflearn.layers.normalization.batch_normalization(x)
        x = tflearn.layers.conv.max_pool_2d(x, 2, 2)

        """ Layer 7 """
        x = tflearn.layers.conv.conv_2d(x, 256, (3, 3), strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', scope="conv1_7")
        x = tflearn.layers.normalization.batch_normalization(x)

        """ Layer 8 """
        x = tflearn.layers.conv.conv_2d(x, 256, (3, 3), strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', scope="conv1_8")
        x = tflearn.layers.normalization.batch_normalization(x)
        x = tflearn.layers.conv.max_pool_2d(x, 2, 2)

        """ Layer 9 """
        x = tflearn.layers.conv.conv_2d(x, 256, (3, 3), strides=2, activation='relu', weight_decay=1e-5, regularizer='L2', scope="conv1_9")
        x = tflearn.layers.normalization.batch_normalization(x)

        """ Layer 10 """
        x = tflearn.layers.conv.conv_2d(x, 256, (3, 3), strides=2, activation='relu', weight_decay=1e-5, regularizer='L2', scope="conv1_10")
        x = tflearn.layers.normalization.batch_normalization(x)
        x = tflearn.layers.conv.max_pool_2d(x, 2, 3)

        x = tflearn.layers.flatten(x)

        return x

    def decoder(self, latent, is_training):

        with tf.variable_scope("auto_predictor_multistep_extended", reuse=tf.AUTO_REUSE):
            latent = tf.expand_dims(latent, axis=1)
            latent = tf.expand_dims(latent, axis=1)

            x = latent

            """ Layer 1 """
            x = tflearn.layers.conv.conv_2d_transpose(x, output_shape=[2, 2], nb_filter=256, filter_size=2, strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', padding='valid', name='decoder_transpose_1')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_1')

            """ Layer 2 """
            x = tflearn.layers.conv.conv_2d_transpose(x, output_shape=[4, 4], nb_filter=256, filter_size=2, strides=2, activation='relu', weight_decay=1e-5, regularizer='L2', name='decoder_transpose_2')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_2')

            """ Layer 3 """
            x = tflearn.layers.conv.conv_2d_transpose(x, nb_filter=256, output_shape=[7, 10], filter_size=4, strides=[1, 2], activation='relu', weight_decay=1e-5, regularizer='L2', padding="valid", name='decoder_transpose_3')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_3')

            """ Layer 4 """
            x = tflearn.layers.conv.conv_2d_transpose(x, nb_filter=256, output_shape=[15, 20], filter_size=[3, 2], strides=2,  activation='relu', weight_decay=1e-5, regularizer='L2', padding="valid", name='decoder_transpose_4')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_4')

            """ Layer 5 """
            x = tflearn.layers.conv.conv_2d_transpose(x, output_shape=[15, 20], nb_filter=256, filter_size=2, strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', name='decoder_transpose_5')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_5')

            """ Layer 6 """
            x = tflearn.layers.conv.conv_2d_transpose(x, output_shape=[15, 20], nb_filter=128, filter_size=2, strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', name='decoder_transpose_6')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_6')

            """ Layer 7 """
            x = tflearn.layers.conv.conv_2d_transpose(x, output_shape=[30, 40], nb_filter=128, filter_size=2, strides=2, activation='relu', weight_decay=1e-5, regularizer='L2', name='decoder_transpose_7')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_7')

            """ Layer 8 """
            x = tflearn.layers.conv.conv_2d_transpose(x, output_shape=[30, 40], nb_filter=128, filter_size=3, strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', name='decoder_transpose_8')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_8')

            """ Layer 9 """
            x = tflearn.layers.conv.conv_2d_transpose(x, output_shape=[60, 80], nb_filter=128, filter_size=3, strides=2, activation='relu',  weight_decay=1e-5, regularizer='L2', name='decoder_transpose_9')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_9')

            """ Layer 10 """
            x = tflearn.layers.conv.conv_2d_transpose(x, output_shape=[60, 80], nb_filter=128, filter_size=3, strides=1, activation='relu', weight_decay=1e-5, regularizer='L2', name='decoder_transpose_10')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_10')

            """ Layer 11 """
            x = tflearn.layers.conv.conv_2d_transpose(x, output_shape=[120, 160], nb_filter=128, filter_size=3, strides=2, activation='relu', weight_decay=1e-5, regularizer='L2', name='decoder_transpose_11')
            x = tflearn.layers.normalization.batch_normalization(x, name='decoder_bn_11')

            """ Layer 12 """
            x = tflearn.layers.conv.conv_2d_transpose(x, output_shape=[120, 160], nb_filter=2, filter_size=3, strides=1, activation='linear', weight_decay=1e-5, regularizer='L2', name='decoder_transpose_12')

            return x

    def interact_mlp(self, pairwise_latent):
        with tf.variable_scope("auto_predictor_multistep_extended", reuse=tf.AUTO_REUSE):
            pairwise_latent = tflearn.layers.core.fully_connected(pairwise_latent, 256, activation='relu', name='f_interact_mlp_fc_1')
            pairwise_latent = tflearn.layers.normalization.batch_normalization(pairwise_latent, name='f_interact_mlp_bn_1')

            # shape of pairwise_latent is (1, 256)
            pairwise_latent = tflearn.layers.core.fully_connected(pairwise_latent, 256, activation='relu', name='f_interact_mlp_fc_2')
            #pairwise_latent = tflearn.layers.normalization.batch_normalization(pairwise_latent, name='f_interact_mlp_bn_2')

        return pairwise_latent

    def f_interact(self, latent):
        """" interaction MLP """
        dataset_name = self.config.tfrecords_dir

        if "5_objects" in dataset_name:
            n_objects = 5
        elif "2_cubes" in dataset_name:
            n_objects = 2
        else:
            n_objects = 3

        """ for testing, the train and batch size can just be set to 1. During training, even if test_batch_size is > 1, we process it in a for loop with batch size 1 which is
        why in this case we need to pad the test batch size in the test_batch cycle (but not in all other validation cycles, in which the batch sizes can all be set to 1)"""

        # shape (n_objects*batch_size, 256) --> (batch_size, n_objects, 256)
        latent_batch = tf.split(latent, num_or_size_splits=self.config.train_batch_size, axis=0)

        f_interact_object_sums = []
        f_interact_total = []

        for object_batch in latent_batch:
            for j in range(n_objects):
                for k in range(n_objects):
                    if j != k:
                        pairwise_latent_a = object_batch[j]
                        pairwise_latent_b = object_batch[k]

                        pairwise_latent_a = tf.expand_dims(pairwise_latent_a, axis=0)
                        pairwise_latent_b = tf.expand_dims(pairwise_latent_b, axis=0)

                        # shape of pairwise_latent is (1, 512)
                        pairwise_latent = tf.concat([pairwise_latent_a, pairwise_latent_b], axis=1)
                        # shape of pairwise_latent is (1, 256)
                        # pairwise_latent = pairwise_latent_a + pairwise_latent_b
                        pairwise_latent = self.interact_mlp(pairwise_latent)

                        f_interact_object_sums.append(pairwise_latent)

            # (n, 256) --> (1, 256), e.g. n=6 for 6 edges (3 objects)
            f_interact_sum_per_batch = tf.reduce_sum(f_interact_object_sums, axis=0)
            # (1, 256) --> (n_objects, 256)
            f_interact_sum_per_batch = tf.tile(f_interact_sum_per_batch, [n_objects, 1])
            f_interact_total.append(f_interact_sum_per_batch)

        # ((batch_size), n_objects, 256) --> (batch_size * n_objects, 256)
        f_interact_total = tf.reshape(f_interact_total, [len(f_interact_total) * n_objects, 256])

        return f_interact_total

    def physics_predictor(self, latent, ctrl):
        with tf.variable_scope("auto_predictor_multistep_extended", reuse=tf.AUTO_REUSE):
            latent_previous_step = latent

            """ control MLP """
            latent_ctrl = tflearn.layers.core.fully_connected(ctrl, 32, activation='relu', name='ctrl_mlp_fc_1')
            latent_ctrl = tflearn.layers.normalization.batch_normalization(latent_ctrl, name='ctrl_mlp_bn_1')

            latent_ctrl = tflearn.layers.core.fully_connected(latent_ctrl, 32, activation='relu', name='ctrl_mlp_fc_2')
            latent_ctrl = tflearn.layers.normalization.batch_normalization(latent_ctrl, name='ctrl_mlp_bn_2')

            latent_ctrl = tflearn.layers.core.fully_connected(latent_ctrl, 32, activation='relu', name="ctrl_mlp_fc_3")
            latent_ctrl = tflearn.layers.normalization.batch_normalization(latent_ctrl, name='ctrl_mlp_bn_3')

            """" transition MLP to next time step """
            latent_next_step = tf.concat([latent, latent_ctrl], axis=-1)
            latent_next_step = tflearn.layers.core.fully_connected(latent_next_step, 256, activation='relu', name='f_trans_mlp_fc_1')
            latent_next_step = tflearn.layers.normalization.batch_normalization(latent_next_step, name='f_trans_mlp_bn_1')

            latent_next_step = tflearn.layers.core.fully_connected(latent_next_step, 256, activation='relu', name='f_trans_mlp_fc_2')

            if self.config.use_f_interact:
                f_interact_total = self.f_interact(latent)
                physics_output = latent_next_step + latent_previous_step + f_interact_total
            else:
                physics_output = latent_next_step + latent_previous_step

            return physics_output

    def cnnmodel(self, in_rgb, in_segxyz, in_control=None, is_training=True, n_predictions=5):
        in_rgb_segxyz = tf.concat([in_rgb, in_segxyz], axis=-1)
        # latent_img has shape (?, 256), e.g. (3*10, 256) 3: n_objects, 10: batch size
        latent_img = self.encoder(in_rgbsegxyz=in_rgb_segxyz, is_training=is_training)

        predictions = []
        out_latent_vectors = []
        # debug
        debug_in_control = []

        in_control_T = tf.split(in_control, num_or_size_splits=n_predictions)
        out_latent_vectors.append(latent_img)

        for i in range(n_predictions):
            # latent_img has shape (?, 256), e.g. (3*10,256) (same as above but here the latent_img is evolving over time)
            latent_img = self.physics_predictor(latent=latent_img, ctrl=in_control_T[i])
            img_decoded = self.decoder(latent=latent_img, is_training=is_training)
            predictions.append(img_decoded)

            # debug
            out_latent_vectors.append(latent_img)
            debug_in_control.append(in_control_T[i])

        predictions = tf.concat(predictions, axis=0)
        out_latent_vectors = tf.concat(out_latent_vectors, axis=0)

        return predictions, in_rgb_segxyz, out_latent_vectors, debug_in_control

    def save(self, sess):
        print("Saving model...")
        self.saver.save(sess, self.config.checkpoint_dir, self.cur_batch_tensor)
        print("Model saved")

    # load latest checkpoint from the experiment path defined in the config file
    def load(self, sess):
        latest_checkpoint = tf.train.latest_checkpoint(self.config.checkpoint_dir)
        if latest_checkpoint:
            print("Loading model checkpoint {} ...".format(latest_checkpoint))
            self.saver.restore(sess, latest_checkpoint)
            print("Model loaded")
        #from tensorflow.python.tools.inspect_checkpoint import print_tensors_in_checkpoint_file
        #print_tensors_in_checkpoint_file(file_name=latest_checkpoint, tensor_name="", all_tensors = False, all_tensor_names = True)

    # just initialize a tensorflow variable to use it as epoch counter
    def init_cur_epoch(self):
        with tf.variable_scope('cur_epoch'):
            self.cur_epoch_tensor = tf.Variable(0, trainable=False, name='cur_epoch')
            self.increment_cur_epoch_tensor = tf.assign(self.cur_epoch_tensor, self.cur_epoch_tensor+1)

    # just initialize a tensorflow variable to use it as global step counter
    def init_global_step(self):
        # DON'T forget to add the global step tensor to the tensorflow trainer
        with tf.variable_scope('global_step'):
            self.global_step_tensor = tf.Variable(0, trainable=False, name='global_step')

    def init_batch_step(self):
        # DON'T forget to add the global step tensor to the tensorflow trainer
        with tf.variable_scope('global_step'):
            self.cur_batch_tensor = tf.Variable(0, trainable=False, name='cur_batch')
            self.increment_cur_batch_tensor = tf.assign(self.cur_batch_tensor, self.cur_batch_tensor+1)


    def init_saver(self):
        self.saver = tf.train.Saver(max_to_keep=self.config.max_checkpoints_to_keep)


    def load_resnet(self, sess):
        tf_initial_checkpoint_v2 = "../models/pretrained_nets/resnet_v2_50/resnet_v2_50.ckpt"
        variables_to_restore_v2 = get_var_list_to_restore_by_name('resnet_v2_50')
        restorer_v2 = tf.train.Saver(variables_to_restore_v2)
        restorer_v2.restore(sess, tf_initial_checkpoint_v2)