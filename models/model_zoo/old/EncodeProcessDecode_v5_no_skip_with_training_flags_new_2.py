# Copyright 2018 The GraphNets Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or  implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Model architectures for the singulation task."""


###
# Description
# ============================================================================
#    as opposed to v2, this model file assumes global attributes to be only the gripper position
#    (instead of position and depth/seg/rgb images)
# ============================================================================
###

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from graph_nets import modules
from base.base_model import BaseModel
from utils.utils import get_correct_image_shape
from graph_nets import utils_tf

import sonnet as snt
import tensorflow as tf


VERBOSITY = True

class EncodeProcessDecode_v5_no_skip_with_training_flags_new_2(snt.AbstractModule, BaseModel):
    """
    Full encode-process-decode model.

    The model we explore includes three components:
    - An "Encoder" graph net, which independently encodes the edge, node, and
    global attributes (does not compute relations etc.).
    - A "Core" graph net, which performs N rounds of processing (message-passing)
    steps. The input to the Core is the concatenation of the Encoder's output
    and the previous output of the Core (labeled "Hidden(t)" below, where "t" is
    the processing step).
    - A "Decoder" graph net, which independently decodes the edge, node, and
    global attributes (does not compute relations etc.), on each message-passing
    step.

                      Hidden(t)   Hidden(t+1)
                         |            ^
            *---------*  |  *------*  |  *---------*
            |         |  |  |      |  |  |         |
  Input --->| Encoder |  *->| Core |--*->| Decoder |---> Output(t)
            |         |---->|      |     |         |
            *---------*     *------*     *---------*
    """
    def __init__(self, config, name="EncodeProcessDecode"):

        super(EncodeProcessDecode_v5_no_skip_with_training_flags_new_2, self).__init__(name=name)

        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_pooling = config.convnet_pooling
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_tanh = config.convnet_tanh
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.depth_data_provided = config.depth_data_provided
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_conv_filters = config.n_conv_filters
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.model_id = config.model_type
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.latent_state_noise = config.latent_state_noise

        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.edge_output_size = config.edge_output_size
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.node_output_size = config.node_output_size
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.global_output_size = config.global_output_size

        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_layers_globals = config.n_layers_globals
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_layers_nodes = config.n_layers_nodes
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_layers_edges = config.n_layers_edges
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_edges = config.n_neurons_edges
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes = config.n_neurons_nodes
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_globals = config.n_neurons_globals
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual = config.n_neurons_nodes_non_visual
        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm = config.conv_layer_instance_norm

        self.config = config
        # init the global step
        self.init_global_step()
        # init the epoch counter
        self.init_cur_epoch()
        # init the batch counter
        self.init_batch_step()

        self.use_cnn = self.config.node_as_cnn

        if self.use_cnn:
            self._encoder = CNNMLPEncoderGraphIndependent(config.model_type)
            self._decoder = CNNMLPDecoderGraphIndependent(config.model_type)
            self._encoder_globals = EncoderGlobalsGraphIndependent(config.model_type)
        else:
            raise TypeError("set flag to >use_cnn<")

        self._core = MLPGraphNetwork(config.model_type)

        self.init_ops()

        self.node_output_size = config.node_output_size  # for future, currently not needed
        self.edge_output_size = config.edge_output_size  # for future, currently not needed
        self.global_output_size = config.global_output_size  # needed

        self.optimizer = tf.train.AdamOptimizer(self.config.learning_rate)

    def _build(self, input_op, target_op, num_processing_steps, is_training):
        print("----- Data used as global attribute: (t, gravity, grippervel, gripperpos) only -----")
        print("----- Visual prediction: segmentation -----")
        print("----- Model uses skip connection: False -----")

        globals = tf.tile(input_op.globals, [3, 1])
        new_input_op = input_op.replace(nodes=tf.concat([input_op.nodes, globals], axis=1))
        latent = self._encoder(new_input_op, is_training)

        output_ops = []

        for step in range(num_processing_steps):
            latent = self._core(latent)
            decoded_op = self._decoder(latent, is_training)
            output_ops.append(decoded_op)
        return output_ops

    # save function that saves the checkpoint in the path defined in the config file
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

    def init_ops(self):
        self.loss_op_train = None
        self.loss_op_test = None

        self.loss_ops_train = None
        self.loss_ops_test = None

        self.pos_vel_loss_ops_test = None
        self.pos_vel_loss_ops_train = None


class MLP_model(snt.AbstractModule):
    def __init__(self, n_neurons, n_layers, output_size, activation_final=True, typ="mlp_layer_norm", name="MLP_model"):
        super(MLP_model, self).__init__(name=name)
        assert typ in ["mlp_layer_norm", "mlp_transform"]
        self.n_neurons = n_neurons
        self.n_layers = n_layers
        self.output_size = output_size
        self.typ = typ
        self.activation_final = activation_final

    def _build(self, inputs):
        if self.typ == "mlp_transform":
            # Transforms the outputs into the appropriate shape.
            net = snt.nets.MLP([self.n_neurons] * self.n_layers, activate_final=self.activation_final)
            seq = snt.Sequential([net, snt.LayerNorm(), snt.Linear(self.output_size)])(inputs)
        elif self.typ == "mlp_layer_norm":
            net = snt.nets.MLP([self.n_neurons] * self.n_layers, activate_final=self.activation_final)
            seq = snt.Sequential([net, snt.LayerNorm()])(inputs)
        return seq


class EncoderGlobalsGraphIndependent(snt.AbstractModule):
    def __init__(self, model_id, name="EncoderGlobalsGraphIndependent"):
        super(EncoderGlobalsGraphIndependent, self).__init__(name=name)
        self.model_id = model_id

        with self._enter_variable_scope():
            self._network = modules.GraphIndependent(
                edge_model_fn=None,
                node_model_fn=None,
                global_model_fn=lambda: get_model_from_config(self.model_id, model_type="mlp")(
                                                                                        n_neurons=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_globals,
                                                                                        n_layers=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_layers_globals,
                                                                                        output_size=None,
                                                                                        activation_final=False,
                                                                                        typ="mlp_layer_norm",
                                                                                        name="mlp_encoder_global"),
            )

    def _build(self, inputs, is_training, verbose=VERBOSITY):
        return self._network(inputs)


class CNNMLPEncoderGraphIndependent(snt.AbstractModule):
    """GraphNetwork with CNN node and MLP edge / global models."""

    def __init__(self, model_id, name="CNNMLPEncoderGraphIndependent"):
        super(CNNMLPEncoderGraphIndependent, self).__init__(name=name)
        self.model_id = model_id

    def _build(self, inputs, is_training, verbose=VERBOSITY):
        self._network = modules.GraphIndependent(
            edge_model_fn=lambda: get_model_from_config(self.model_id, model_type="mlp")(
                                                                n_neurons=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_edges,
                                                                n_layers=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_layers_edges,
                                                                output_size=None,
                                                                typ="mlp_layer_norm",
                                                                activation_final=False,
                                                                name="mlp_encoder_edge"),

            node_model_fn=lambda: VisualAndLatentEncoderSonnet(name="visual_and_latent_node_encoder", is_training=is_training),

            global_model_fn=None
        )
        return self._network(inputs)


class CNNMLPDecoderGraphIndependent(snt.AbstractModule):
    """Graph decoder network with Transpose CNN node and MLP edge / global models."""
    def __init__(self, model_id,  name="CNNMLPDecoderGraphIndependent"):
        super(CNNMLPDecoderGraphIndependent, self).__init__(name=name)
        self.model_id = model_id

    def _build(self, inputs, is_training, verbose=VERBOSITY):
        self._network = modules.GraphIndependent(
            edge_model_fn=lambda: get_model_from_config(model_id=self.model_id, model_type="mlp")(
                                                        n_neurons=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_edges,
                                                        n_layers=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_layers_edges,
                                                        output_size=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.edge_output_size,
                                                        typ="mlp_transform",
                                                        activation_final=False,
                                                        name="mlp_decoder_edge"),

            node_model_fn=lambda: VisualAndLatentDecoderSonnet(name="visual_and_latent_node_decoder", is_training=is_training),

            global_model_fn=lambda: get_model_from_config(model_id=self.model_id, model_type="mlp")(
                                                        n_neurons=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_globals,
                                                        n_layers=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_layers_globals,
                                                        output_size=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.global_output_size,
                                                        typ="mlp_transform",
                                                        activation_final=False,
                                                        name="mlp_decoder_global")
        )

        return self._network(inputs)


class MLPGraphNetwork(snt.AbstractModule):
    """GraphNetwork with MLP edge, node, and global models."""

    def __init__(self, model_id, name="MLPGraphNetwork"):
        super(MLPGraphNetwork, self).__init__(name=name)
        with self._enter_variable_scope():
          self._network = modules.GraphNetwork(
              edge_model_fn=lambda: get_model_from_config(model_id, model_type="mlp")(n_neurons=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_edges,
                                                                                      n_layers=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_layers_edges,
                                                                                      output_size=None,
                                                                                      typ="mlp_layer_norm",
                                                                                      name="mlp_core_edge"),
              node_model_fn=lambda: get_model_from_config(model_id, model_type="mlp")(n_neurons=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes,
                                                                                      n_layers=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_layers_nodes,
                                                                                      output_size=None,
                                                                                      typ="mlp_layer_norm",
                                                                                      activation_final=False,
                                                                                      name="mlp_core_node"),

              global_model_fn=lambda: get_model_from_config(model_id, model_type="mlp")(n_neurons=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_globals,
                                                                                        n_layers=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_layers_globals,
                                                                                        output_size=None,
                                                                                        typ="mlp_layer_norm",
                                                                                        name="mlp_core_global")
          )

    def _build(self, inputs):
        return self._network(inputs)


class Decoder5LayerConvNet2D(snt.AbstractModule):
    def __init__(self, is_training, name='decoder_convnet2d'):
        super(Decoder5LayerConvNet2D, self).__init__(name=name)
        self.is_training = is_training

    def _build(self, inputs, name, verbose=VERBOSITY, keep_dropout_prop=0.9):
        return NotImplementedError


class Encoder5LayerConvNet2D(snt.AbstractModule):
    def __init__(self, is_training, name="encoder_convnet2d"):
        super(Encoder5LayerConvNet2D, self).__init__(name=name)
        self.is_training = is_training

    def _build(self, inputs, name, verbose=VERBOSITY, keep_dropout_prop=0.9):
        return NotImplementedError


class VisualAndLatentDecoder(snt.AbstractModule):
    def __init__(self, name='VisualAndLatentDecoder'):
        super(VisualAndLatentDecoder, self).__init__(name=name)
        self._name = name

    def _build(self, inputs, is_training=False, verbose=VERBOSITY, keep_dropout_prop=0.9):
        filter_sizes = [EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_conv_filters,
                        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_conv_filters * 2]

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_tanh:
            activation = tf.nn.tanh
        else:
            activation = tf.nn.relu

        """ get image data, get everything >except< last n elements which are non-visual (position and velocity) """
        # image_data = inputs[:, :-EncodeProcessDecode_v5_no_skip_no_core.n_neurons_nodes_non_visual]
        image_data = inputs

        """ in order to apply 2D convolutions, transform shape (batch_size, features) -> shape (batch_size, 1, 1, features)"""
        image_data = tf.expand_dims(image_data, axis=1)
        image_data = tf.expand_dims(image_data, axis=1)  # yields shape (?,1,1,latent_dim)

        ''' layer 0 (1,1,latent_dim) -> (2,2,filter_sizes[1])'''
        outputs = tf.layers.conv2d_transpose(image_data, filters=filter_sizes[1], kernel_size=2, strides=2, padding='valid',
                                             activation=activation, use_bias=False,
                                             kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)
        l01_shape = outputs.get_shape()

        ''' layer 0_1 (2,2,latent_dim) -> (4,4,filter_sizes[1])'''
        outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[1], kernel_size=2, strides=2, padding='valid',
                                             activation=activation, use_bias=False,
                                             kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)
        l02_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 0_2 (4,4,latent_dim) -> (7,10,filter_sizes[1])'''
        outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[1], kernel_size=[4, 4], strides=[1, 2], padding='valid',
                                             activation=activation, use_bias=False,
                                             kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l1_shape = outputs.get_shape()

        ''' layer 2 (7,10,filter_sizes[1]) -> (15,20,filter_sizes[1]) '''
        outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[1], kernel_size=(3, 2), strides=2, padding='valid',
                                             activation=activation, use_bias=False,
                                             kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l2_shape = outputs.get_shape()

        # outputsl2 = outputs
        # ''' layer 2_2 (15,20,filter_sizes[1] -> (15,20,filter_sizes[1]) '''
        # --------------- SKIP CONNECTION CONCAT --------------- #
        # outputs = tf.concat([outputs, self.skip3], axis=3)
        # outputs = outputs + self.skip3
        # after_skip3 = outputs.get_shape()
        # --------------- SKIP CONNECTION ADD --------------- #
        # outputs = tf.layers.conv2d(self.skip3, filters=filter_sizes[1], kernel_size=3, strides=1, padding='same', activation=activation)
        # outputs = tf.contrib.layers.layer_norm(outputs)
        # l1_2_shape = outputs.get_shape()
        # outputs = outputsl2 + outputs
        # after_skip3 = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 3 (15,20,filter_sizes[1]) -> (15,20,filter_sizes[1]) '''
        outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[1], kernel_size=2, strides=1, padding='same',
                                             activation=activation, use_bias=False,
                                             kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l3_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 5 (15,20,filter_sizes[1]) -> (30,40,filter_sizes[1]) '''
        outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[0], kernel_size=2, strides=1, padding='same',
                                             activation=activation, use_bias=False,
                                             kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)
        l5_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 6 (30,40,filter_sizes[1]) -> (30,40,filter_sizes[1]) '''
        outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[0], kernel_size=2, strides=2, padding='same',
                                             activation=activation, use_bias=False,
                                             kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l6_shape = outputs.get_shape()

        ''' layer 7 (30,40,filter_sizes[1]) -> (30,40,filter_sizes[1]) '''
        outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
                                   use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l7_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 8 (30,40,filter_sizes[1]) -> (30,40,filter_sizes[0]) '''
        outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same',
                                             activation=activation, use_bias=False,
                                             kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l8_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 9 (30,40,filter_sizes[0]) -> (60,80,filter_sizes[0]) '''
        outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[0], kernel_size=3, strides=2, padding='same',
                                             activation=activation, use_bias=False,
                                             kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l9_shape = outputs.get_shape()

        ''' layer 10 (60,80,filter_sizes[0]) -> (60,80,filter_sizes[0]) '''
        outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
                                   use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l10_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 11 (60,80,filter_sizes[0])  -> (60,80,filter_sizes[0]) '''
        outputs = tf.layers.conv2d_transpose(outputs, filters=64, kernel_size=3, strides=1, padding='same', activation=activation,
                                             use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l11_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 12 (60,80,filter_sizes[0]) -> (120,160,filter_sizes[0]) '''
        outputs = tf.layers.conv2d_transpose(outputs, filters=64, kernel_size=3, strides=2, padding='same', activation=activation,
                                             use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l12_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)


        ''' layer 13 (120,160,filter_sizes[0]) -> (120,160,filter_sizes[0]) '''
        outputs = tf.layers.conv2d(outputs, filters=64, kernel_size=3, strides=1, padding='same', activation=activation, use_bias=False,
                                   kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l13_shape = outputs.get_shape()

        # outputs = outputs1 + outputs

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 14 (120,160,filter_sizes[0]) -> (120,160,filter_sizes[0]) '''
        outputs = tf.layers.conv2d_transpose(outputs, filters=64, kernel_size=3, strides=1, padding='same', activation=activation,
                                             use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l14_shape = outputs.get_shape()

        ''' layer 15 (120,160,filter_sizes[0]) -> (120,160,1) '''
        outputs = tf.layers.conv2d(outputs, filters=2, kernel_size=3, strides=1, padding='same', activation=None, use_bias=False,
                                   kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))
        l15_shape = outputs.get_shape()

        visual_latent_output = tf.layers.flatten(outputs)

        if verbose:
            print("Latent visual data shape", image_data.get_shape())
            print("Layer01 decoder output shape", l01_shape)
            print("Layer02 decoder output shape", l02_shape)
            print("Layer1 decoder output shape", l1_shape)
            print("Layer2 decoder output shape", l2_shape)
            print("Layer3 decoder output shape", l3_shape)
            print("Layer4 decoder output shape", l5_shape)
            print("Layer5 decoder output shape", l6_shape)
            print("Layer6 decoder output shape", l7_shape)
            print("Layer7 decoder output shape", l8_shape)
            print("Layer8 decoder output shape", l9_shape)
            print("Layer9 decoder output shape", l10_shape)
            print("Layer10 decoder output shape", l11_shape)
            print("Layer11 decoder output shape", l12_shape)
            print("Layer12 decoder output shape", l13_shape)
            print("Layer13 decoder output shape", l14_shape)
            print("Layer14 decoder output shape", l15_shape)
            print("decoder shape before adding non-visual data", visual_latent_output.get_shape())  # print("shape before skip3 {}".format(l1_shape))  # print("shape after skip3 {}".format(after_skip3))  # print("shape before skip2 {}".format(l11_shape))  # print("shape after skip2 {}".format(after_skip2))  # print("shape before skip1 {}".format(l17_shape))  # print("shape after skip1 {}".format(after_skip1))


        n_non_visual_elements = 6
        """ get x,y,z-position and x,y,z-velocity from n_neurons_nodes_non_visual-dimensional space """
        non_visual_latent_output = inputs[:, -EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual:]

        # Transforms the outputs into the appropriate shape.
        """ map latent position/velocity (nodes) from 32d to original 6d space """
        n_neurons = EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual
        n_layers = 2
        net = snt.nets.MLP([n_neurons] * n_layers, activate_final=False)
        non_visual_decoded_output = snt.Sequential([net, snt.LayerNorm(), snt.Linear(n_non_visual_elements)])(non_visual_latent_output)

        """ concatenate 6d space latent data with visual data 
        (dimensions if segmentation image only: (?, 19200)) """
        outputs = tf.concat([visual_latent_output, non_visual_decoded_output], axis=1)

        if verbose:
            print("shape decoded output (visual):", visual_latent_output.get_shape())
            print("shape decoded output (latent):", non_visual_decoded_output.get_shape())
            print("final decoder output shape after including non-visual data", outputs.get_shape())

        return outputs


class VisualAndLatentDecoderSonnet(snt.AbstractModule):
    def __init__(self, name='VisualAndLatentDecoder', is_training=False):
        super(VisualAndLatentDecoderSonnet, self).__init__(name=name)
        self._name = name
        self._is_training = is_training

    def _build(self, inputs, verbose=VERBOSITY, keep_dropout_prop=0.9):
        filter_sizes = [EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_conv_filters,
                        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_conv_filters * 2]

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_tanh:
            activation = tf.nn.tanh
        else:
            activation = tf.nn.relu

        """ get image data, get everything >except< last n elements which are non-visual (position and velocity) """
        # image_data = inputs[:, :-EncodeProcessDecode_v5_no_skip_no_core.n_neurons_nodes_non_visual]
        image_data = inputs

        """ in order to apply 2D convolutions, transform shape (batch_size, features) -> shape (batch_size, 1, 1, features)"""
        image_data = tf.expand_dims(image_data, axis=1)
        image_data = tf.expand_dims(image_data, axis=1)  # yields shape (?,1,1,latent_dim)

        ''' layer 0 (1,1,latent_dim) -> (2,2,filter_sizes[1])'''
        outputs = snt.Conv2DTranspose(output_channels=filter_sizes[1], kernel_shape=2, stride=1, padding="VALID")(image_data)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(image_data, filters=filter_sizes[1], kernel_size=2, strides=2, padding='valid',
        #                                    activation=activation, use_bias=False,
        #                                     kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)
        l01_shape = outputs.get_shape()

        ''' layer 0_1 (2,2,latent_dim) -> (4,4,filter_sizes[1])'''
        outputs = snt.Conv2DTranspose(output_channels=filter_sizes[1], kernel_shape=2, stride=2, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[1], kernel_size=2, strides=2, padding='valid',
        #                                     activation=activation, use_bias=False,
        #                                     kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)
        l02_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 0_2 (4,4,latent_dim) -> (7,10,filter_sizes[1])'''
        outputs = tf.image.resize_bilinear(outputs, [7, 10], align_corners=True)
        #outputs = snt.Conv2DTranspose(output_channels=filter_sizes[1], output_shape=[7, 10], kernel_shape=4, stride=[1, 2], padding="VALID")(outputs)
        #outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[1], kernel_size=[4, 4], strides=[1, 2], padding='valid',
        #                                     activation=activation, use_bias=False,
        #                                     kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l1_shape = outputs.get_shape()

        ''' layer 2 (7,10,filter_sizes[1]) -> (15,20,filter_sizes[1]) '''
        outputs = snt.Conv2DTranspose(output_channels=filter_sizes[1], output_shape=[15, 20], kernel_shape=[3, 2], stride=2, padding="VALID")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[1], kernel_size=(3, 2), strides=2, padding='valid',
        #                                     activation=activation, use_bias=False,
        #                                     kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l2_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 3 (15,20,filter_sizes[1]) -> (15,20,filter_sizes[1]) '''
        outputs = snt.Conv2DTranspose(output_channels=filter_sizes[1], kernel_shape=2, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[1], kernel_size=2, strides=1, padding='same',
        #                                     activation=activation, use_bias=False,
        #                                     kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l3_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 5 (15,20,filter_sizes[1]) -> (30,40,filter_sizes[1]) '''
        outputs = snt.Conv2DTranspose(output_channels=filter_sizes[0], kernel_shape=2, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[0], kernel_size=2, strides=1, padding='same',
        #                                     activation=activation, use_bias=False,
        #                                     kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)
        l5_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 6 (30,40,filter_sizes[1]) -> (30,40,filter_sizes[1]) '''
        outputs = snt.Conv2DTranspose(output_channels=filter_sizes[0], kernel_shape=2, stride=2, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[0], kernel_size=2, strides=2, padding='same',
        #                                     activation=activation, use_bias=False,
        #                                     kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l6_shape = outputs.get_shape()

        ''' layer 7 (30,40,filter_sizes[1]) -> (30,40,filter_sizes[1]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[0], kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
        #                           use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l7_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 8 (30,40,filter_sizes[1]) -> (30,40,filter_sizes[0]) '''
        outputs = snt.Conv2DTranspose(output_channels=filter_sizes[0], kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same',
        #                                     activation=activation, use_bias=False,
        #                                     kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l8_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 9 (30,40,filter_sizes[0]) -> (60,80,filter_sizes[0]) '''
        outputs = snt.Conv2DTranspose(output_channels=filter_sizes[0], kernel_shape=3, stride=2, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=filter_sizes[0], kernel_size=3, strides=2, padding='same',
        #                                     activation=activation, use_bias=False,
        #                                     kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l9_shape = outputs.get_shape()

        ''' layer 10 (60,80,filter_sizes[0]) -> (60,80,filter_sizes[0]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[0], kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
        #                           use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l10_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 11 (60,80,filter_sizes[0])  -> (60,80,filter_sizes[0]) '''
        outputs = snt.Conv2DTranspose(output_channels=128, kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=64, kernel_size=3, strides=1, padding='same', activation=activation,
        #                                     use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l11_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 12 (60,80,filter_sizes[0]) -> (120,160,filter_sizes[0]) '''
        outputs = snt.Conv2DTranspose(output_channels=128, kernel_shape=3, stride=2, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=64, kernel_size=3, strides=2, padding='same', activation=activation,
        #                                     use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l12_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)


        ''' layer 13 (120,160,filter_sizes[0]) -> (120,160,filter_sizes[0]) '''
        outputs = snt.Conv2D(output_channels=128, kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=64, kernel_size=3, strides=1, padding='same', activation=activation, use_bias=False,
        #                           kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l13_shape = outputs.get_shape()

        # outputs = outputs1 + outputs

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' layer 14 (120,160,filter_sizes[0]) -> (120,160,filter_sizes[0]) '''
        outputs = snt.Conv2DTranspose(output_channels=128, kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d_transpose(outputs, filters=64, kernel_size=3, strides=1, padding='same', activation=activation,
        #                                     use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l14_shape = outputs.get_shape()

        ''' layer 15 (120,160,filter_sizes[0]) -> (120,160,2) '''
        outputs = snt.Conv2D(output_channels=2, kernel_shape=3, stride=1, padding="SAME")(outputs)
        #outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=2, kernel_size=3, strides=1, padding='same', activation=None, use_bias=False,
        #                           kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))
        l15_shape = outputs.get_shape()

        #visual_latent_output = tf.layers.flatten(outputs)
        visual_latent_output = snt.BatchFlatten()(outputs)


        if verbose:
            print("Latent visual data shape", image_data.get_shape())
            print("Layer01 decoder output shape", l01_shape)
            print("Layer02 decoder output shape", l02_shape)
            print("Layer1 decoder output shape", l1_shape)
            print("Layer2 decoder output shape", l2_shape)
            print("Layer3 decoder output shape", l3_shape)
            print("Layer4 decoder output shape", l5_shape)
            print("Layer5 decoder output shape", l6_shape)
            print("Layer6 decoder output shape", l7_shape)
            print("Layer7 decoder output shape", l8_shape)
            print("Layer8 decoder output shape", l9_shape)
            print("Layer9 decoder output shape", l10_shape)
            print("Layer10 decoder output shape", l11_shape)
            print("Layer11 decoder output shape", l12_shape)
            print("Layer12 decoder output shape", l13_shape)
            print("Layer13 decoder output shape", l14_shape)
            print("Layer14 decoder output shape", l15_shape)
            print("decoder shape before adding non-visual data", visual_latent_output.get_shape())  # print("shape before skip3 {}".format(l1_shape))  # print("shape after skip3 {}".format(after_skip3))  # print("shape before skip2 {}".format(l11_shape))  # print("shape after skip2 {}".format(after_skip2))  # print("shape before skip1 {}".format(l17_shape))  # print("shape after skip1 {}".format(after_skip1))


        n_non_visual_elements = 6
        """ get x,y,z-position and x,y,z-velocity from n_neurons_nodes_non_visual-dimensional space """
        non_visual_latent_output = inputs[:, -EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual:]

        # Transforms the outputs into the appropriate shape.
        """ map latent position/velocity (nodes) from 32d to original 6d space """
        n_neurons = EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual
        n_layers = 2
        net = snt.nets.MLP([n_neurons] * n_layers, activate_final=False)
        non_visual_decoded_output = snt.Sequential([net, snt.LayerNorm(), snt.Linear(n_non_visual_elements)])(non_visual_latent_output)

        """ concatenate 6d space latent data with visual data 
        (dimensions if segmentation image only: (?, 19200)) """
        outputs = tf.concat([visual_latent_output, non_visual_decoded_output], axis=1)

        if verbose:
            print("shape decoded output (visual):", visual_latent_output.get_shape())
            print("shape decoded output (latent):", non_visual_decoded_output.get_shape())
            print("final decoder output shape after including non-visual data", outputs.get_shape())

        return outputs

class VisualAndLatentEncoderSonnet(snt.AbstractModule):
    def __init__(self, name='VisualAndLatentEncoder', is_training=False):
        super(VisualAndLatentEncoderSonnet, self).__init__(name=name)
        self._name = name
        self._is_training = is_training

    def _build(self, inputs, verbose=VERBOSITY, keep_dropout_prop=0.9):

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_tanh:
            activation = tf.nn.tanh
        else:
            activation = tf.nn.relu

        """ velocity (x,y,z) and position (x,y,z) """
        n_globals = 9
        n_non_visual_elements = 6

        filter_sizes = [EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_conv_filters,
                        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_conv_filters * 2]

        """ shape: (batch_size, features), get everything except velocity and position """
        img_data = inputs[:, :-(n_non_visual_elements + n_globals)]
        img_shape = get_correct_image_shape(config=None, get_type="all",
                                            depth_data_provided=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.depth_data_provided)
        img_data = tf.reshape(img_data, [-1, *img_shape])  # -1 means "all", i.e. batch dimension

        ''' Layer1 encoder output shape (?, 120, 160, filter_sizes[0]) '''
        outputs1 = snt.Conv2D(output_channels=128, kernel_shape=3, stride=1, padding="SAME")(img_data)
        outputs1 = activation(outputs1)
        #outputs1 = tf.layers.conv2d(img_data, filters=64, kernel_size=3, strides=1, padding='same', activation=activation, use_bias=False,
        #                            kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs1 = snt.BatchNorm()(outputs1, is_training=self._is_training)
            #outputs1 = tf.contrib.layers.instance_norm(outputs1)

        l1_shape = outputs1.get_shape()

        ''' Layer2 encoder output shape (?, 120, 160, filter_sizes[0]) '''
        outputs = snt.Conv2D(output_channels=128, kernel_shape=3, stride=1, padding="SAME")(outputs1)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs1, filters=64, kernel_size=3, strides=1, padding='same', activation=activation, use_bias=False,
        #                           kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        #if EncodeProcessDecode_v5_no_skip_no_core_no_training_flags_new.conv_layer_instance_norm:
        #    outputs = tf.contrib.layers.instance_norm(outputs)

        l2_shape = outputs.get_shape()

        ''' Layer3 encoder output shape (?, 60, 80, filter_sizes[0]) '''
        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_pooling:
            outputs = tf.layers.max_pooling2d(outputs, 2, 2)
        l3_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' Layer4 encoder output shape (?, 60, 80, filter_sizes[0]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[0], kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
        #                           use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l4_shape = outputs.get_shape()

        ''' Layer5 encoder output shape (?, 60, 80, filter_sizes[0]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[0], kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
        #                           use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        # --------------- SKIP CONNECTION --------------- #
        outputs2 = outputs

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l5_shape = outputs.get_shape()

        ''' Layer6 encoder output shape (?, 30, 40, filter_sizes[0]) '''
        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_pooling:
            outputs = tf.layers.max_pooling2d(outputs, 2, 2)
        l6_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' Layer7 encoder output shape (?, 30, 40, filter_sizes[1]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[0], kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
        #                           use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l7_shape = outputs.get_shape()

        ''' Layer8 encoder output shape (?, 30, 40, filter_sizes[0]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[0], kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
        #                           use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l8_shape = outputs.get_shape()

        ''' Layer9 encoder output shape (?, 15, 20, filter_sizes[0]) '''
        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_pooling:
            outputs = tf.layers.max_pooling2d(outputs, 2, 2)
        l9_shape = outputs.get_shape()

        #if is_training:
        #    outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        #else:
        #    outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' Layer10 encoder output shape (?, 15, 20, filter_sizes[1]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[1], kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=filter_sizes[1], kernel_size=3, strides=1, padding='same', activation=activation,
        #                           use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l10_shape = outputs.get_shape()

        ''' Layer11 encoder output shape (?, 15, 20, filter_sizes[1]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[1], kernel_shape=3, stride=1, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=filter_sizes[1], kernel_size=3, strides=1, padding='same', activation=activation,
        #                           use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))
        # --------------- SKIP CONNECTION --------------- #
        outputs3 = outputs

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l11_shape = outputs.get_shape()

        ''' Layer12 encoder output shape (?, 7, 10, filter_sizes[1]) '''
        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_pooling:
            outputs = tf.layers.max_pooling2d(outputs, 2, 2)
        l12_shape = outputs.get_shape()

        ''' Layer13 encoder output shape (?, 4, 5, filter_sizes[1]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[1], kernel_shape=3, stride=2, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=filter_sizes[1], kernel_size=3, strides=2, padding='same', activation=activation,
        #                           use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l13_shape = outputs.get_shape()

        ''' Layer14 encoder output shape (?, 2, 3, filter_sizes[1]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[1], kernel_shape=3, stride=2, padding="SAME")(outputs)
        outputs = activation(outputs)
        #outputs = tf.layers.conv2d(outputs, filters=filter_sizes[1], kernel_size=3, strides=2, padding='same', activation=activation,
        #                           use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = snt.BatchNorm()(outputs, is_training=self._is_training)
            #outputs = tf.contrib.layers.instance_norm(outputs)

        l14_shape = outputs.get_shape()

        ''' Layer15 encoder output shape (?, 1, 1, filter_sizes[1]) '''
        ''' Layer14 encoder output shape (?, 2, 3, filter_sizes[1]) '''
        outputs = snt.Conv2D(output_channels=filter_sizes[1], kernel_shape=2, stride=2, padding="VALID")(outputs)
        outputs = activation(outputs)
        l15_shape = outputs.get_shape()

        if verbose:
            print("Layer1 encoder output shape", l1_shape)
            print("Layer2 encoder output shape", l2_shape)
            print("Layer3 encoder output shape", l3_shape)
            print("Layer4 encoder output shape", l4_shape)
            print("Layer5 encoder output shape", l5_shape)
            print("Layer6 encoder output shape", l6_shape)
            print("Layer7 encoder output shape", l7_shape)
            print("Layer8 encoder output shape", l8_shape)
            print("Layer9 encoder output shape", l9_shape)
            print("Layer10 encoder output shape", l10_shape)
            print("Layer11 encoder output shape", l11_shape)
            print("Layer12 encoder output shape", l12_shape)
            print("Layer13 encoder output shape", l13_shape)
            print("Layer14 encoder output shape", l14_shape)
            print("Layer15 encoder output shape", l15_shape)

        # ' shape (?, 7, 10, filter_sizes[1]) -> (?, n_neurons_nodes_total_dim-n_neurons_nodes_non_visual) '
        visual_latent_output = tf.layers.flatten(outputs)
        # visual_latent_output = tf.layers.dense(inputs=visual_latent_output, units=EncodeProcessDecode_v4_172_improve_shapes_exp1.n_neurons_nodes_total_dim - EncodeProcessDecode_v4_172_improve_shapes_exp1.n_neurons_nodes_non_visual)

        # --------------- SKIP CONNECTION --------------- #
        self.skip1 = outputs1
        self.skip2 = outputs2
        self.skip3 = outputs3


        n_globals = 9
        n_non_visual_elements = 6

        gripper_input = inputs[:, -n_globals:]  # get x,y,z-gripper position and x,y,z-gripper velocity

        n_neurons = EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual
        n_layers = EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual
        output_size = EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual
        net = snt.nets.MLP([n_neurons] * n_layers, activate_final=False)
        """ map velocity and position into a latent space, concatenate with visual latent space vector """
        gripper_latent_output = snt.Sequential([net, snt.LayerNorm(), snt.Linear(output_size)])(gripper_input)

        outputs = tf.concat([visual_latent_output, gripper_latent_output], axis=1)

        if verbose:
            print("final encoder output shape", outputs.get_shape())

        return outputs


class VisualAndLatentEncoder(snt.AbstractModule):
    def __init__(self, name='VisualAndLatentEncoder'):
        super(VisualAndLatentEncoder, self).__init__(name=name)
        self._name = name

    def _build(self, inputs, is_training=False, verbose=VERBOSITY, keep_dropout_prop=0.9):

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_tanh:
            activation = tf.nn.tanh
        else:
            activation = tf.nn.relu

        """ velocity (x,y,z) and position (x,y,z) """
        n_globals = 9
        n_non_visual_elements = 6

        filter_sizes = [EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_conv_filters,
                        EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_conv_filters * 2]

        """ shape: (batch_size, features), get everything except velocity and position """
        img_data = inputs[:, :-(n_non_visual_elements + n_globals)]
        img_shape = get_correct_image_shape(config=None, get_type="all",
                                            depth_data_provided=EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.depth_data_provided)
        img_data = tf.reshape(img_data, [-1, *img_shape])  # -1 means "all", i.e. batch dimension

        ''' Layer1 encoder output shape (?, 120, 160, filter_sizes[0]) '''
        outputs1 = tf.layers.conv2d(img_data, filters=64, kernel_size=3, strides=1, padding='same', activation=activation, use_bias=False,
                                    kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs1 = tf.contrib.layers.instance_norm(outputs1)

        l1_shape = outputs1.get_shape()

        ''' Layer2 encoder output shape (?, 120, 160, filter_sizes[0]) '''
        outputs = tf.layers.conv2d(outputs1, filters=64, kernel_size=3, strides=1, padding='same', activation=activation, use_bias=False,
                                   kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l2_shape = outputs.get_shape()

        ''' Layer3 encoder output shape (?, 60, 80, filter_sizes[0]) '''
        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_pooling:
            outputs = tf.layers.max_pooling2d(outputs, 2, 2)
        l3_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' Layer4 encoder output shape (?, 60, 80, filter_sizes[0]) '''
        outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
                                   use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l4_shape = outputs.get_shape()

        ''' Layer5 encoder output shape (?, 60, 80, filter_sizes[0]) '''
        outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
                                   use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        # --------------- SKIP CONNECTION --------------- #
        outputs2 = outputs

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l5_shape = outputs.get_shape()

        ''' Layer6 encoder output shape (?, 30, 40, filter_sizes[0]) '''
        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_pooling:
            outputs = tf.layers.max_pooling2d(outputs, 2, 2)
        l6_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' Layer7 encoder output shape (?, 30, 40, filter_sizes[1]) '''
        outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
                                   use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l7_shape = outputs.get_shape()

        ''' Layer8 encoder output shape (?, 30, 40, filter_sizes[0]) '''
        outputs = tf.layers.conv2d(outputs, filters=filter_sizes[0], kernel_size=3, strides=1, padding='same', activation=activation,
                                   use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l8_shape = outputs.get_shape()

        ''' Layer9 encoder output shape (?, 15, 20, filter_sizes[0]) '''
        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_pooling:
            outputs = tf.layers.max_pooling2d(outputs, 2, 2)
        l9_shape = outputs.get_shape()

        if is_training:
            outputs = tf.nn.dropout(outputs, keep_prob=keep_dropout_prop)
        else:
            outputs = tf.nn.dropout(outputs, keep_prob=1.0)

        ''' Layer10 encoder output shape (?, 15, 20, filter_sizes[1]) '''
        outputs = tf.layers.conv2d(outputs, filters=filter_sizes[1], kernel_size=3, strides=1, padding='same', activation=activation,
                                   use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l10_shape = outputs.get_shape()

        ''' Layer11 encoder output shape (?, 15, 20, filter_sizes[1]) '''
        outputs = tf.layers.conv2d(outputs, filters=filter_sizes[1], kernel_size=3, strides=1, padding='same', activation=activation,
                                   use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))
        # --------------- SKIP CONNECTION --------------- #
        outputs3 = outputs

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l11_shape = outputs.get_shape()

        ''' Layer12 encoder output shape (?, 7, 10, filter_sizes[1]) '''
        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_pooling:
            outputs = tf.layers.max_pooling2d(outputs, 2, 2)
        l12_shape = outputs.get_shape()

        ''' Layer13 encoder output shape (?, 4, 5, filter_sizes[1]) '''
        outputs = tf.layers.conv2d(outputs, filters=filter_sizes[1], kernel_size=3, strides=2, padding='same', activation=activation,
                                   use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l13_shape = outputs.get_shape()

        ''' Layer14 encoder output shape (?, 2, 3, filter_sizes[1]) '''
        outputs = tf.layers.conv2d(outputs, filters=filter_sizes[1], kernel_size=3, strides=2, padding='same', activation=activation,
                                   use_bias=False, kernel_regularizer=tf.contrib.layers.l2_regularizer(scale=1e-05))

        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.conv_layer_instance_norm:
            outputs = tf.contrib.layers.instance_norm(outputs)

        l14_shape = outputs.get_shape()

        ''' Layer15 encoder output shape (?, 1, 1, filter_sizes[1]) '''
        if EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.convnet_pooling:
            outputs = tf.layers.max_pooling2d(outputs, 2, 2)
        l15_shape = outputs.get_shape()

        if verbose:
            print("Layer1 encoder output shape", l1_shape)
            print("Layer2 encoder output shape", l2_shape)
            print("Layer3 encoder output shape", l3_shape)
            print("Layer4 encoder output shape", l4_shape)
            print("Layer5 encoder output shape", l5_shape)
            print("Layer6 encoder output shape", l6_shape)
            print("Layer7 encoder output shape", l7_shape)
            print("Layer8 encoder output shape", l8_shape)
            print("Layer9 encoder output shape", l9_shape)
            print("Layer10 encoder output shape", l10_shape)
            print("Layer11 encoder output shape", l11_shape)
            print("Layer12 encoder output shape", l12_shape)
            print("Layer13 encoder output shape", l13_shape)
            print("Layer14 encoder output shape", l14_shape)
            print("Layer15 encoder output shape", l15_shape)

        # ' shape (?, 7, 10, filter_sizes[1]) -> (?, n_neurons_nodes_total_dim-n_neurons_nodes_non_visual) '
        visual_latent_output = tf.layers.flatten(outputs)
        # visual_latent_output = tf.layers.dense(inputs=visual_latent_output, units=EncodeProcessDecode_v4_172_improve_shapes_exp1.n_neurons_nodes_total_dim - EncodeProcessDecode_v4_172_improve_shapes_exp1.n_neurons_nodes_non_visual)

        # --------------- SKIP CONNECTION --------------- #
        self.skip1 = outputs1
        self.skip2 = outputs2
        self.skip3 = outputs3


        n_globals = 9
        n_non_visual_elements = 6

        gripper_input = inputs[:, -n_globals:]  # get x,y,z-gripper position and x,y,z-gripper velocity

        n_neurons = EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual
        n_layers = EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual
        output_size = EncodeProcessDecode_v5_no_skip_with_training_flags_new_2.n_neurons_nodes_non_visual
        net = snt.nets.MLP([n_neurons] * n_layers, activate_final=False)
        """ map velocity and position into a latent space, concatenate with visual latent space vector """
        gripper_latent_output = snt.Sequential([net, snt.LayerNorm(), snt.Linear(output_size)])(gripper_input)

        outputs = tf.concat([visual_latent_output, gripper_latent_output], axis=1)

        if verbose:
            print("final encoder output shape", outputs.get_shape())

        return outputs


def get_model_from_config(model_id, model_type="mlp"):
    """ cnn2d case """
    if "cnn2d" in model_id and model_type == "visual_encoder":
        return Encoder5LayerConvNet2D
    if "cnn2d" in model_id and model_type == "visual_and_latent_encoder":
        return VisualAndLatentEncoder
    if "cnn2d" in model_id and model_type == "visual_decoder":
        return Decoder5LayerConvNet2D
    if "cnn2d" in model_id and model_type == "visual_and_latent_decoder":
        return VisualAndLatentDecoder
    if "cnn2d" in model_id and model_type == "mlp":
        return MLP_model
