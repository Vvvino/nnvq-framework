#!/home/ga96yar/tensorflow_env/bin/python
# coding: utf-8
import tensorflow as tf
import os
import pandas as pd
import re
import numpy as np
import string
from kaldi_io import kaldi_io
from KaldiHelper.IteratorHelper import DataIterator
from KaldiHelper.MiscHelper import Misc

# TODO no path and file checking so far

class TrainedModel(object):
    def __init__(self, meta_file, stats_file, cond_prob_file, transform_prob=True, log_output=True):
        # define some fields
        self.transform = transform_prob     # transform prob to continuous probability (default=True)
        self.log_ouput = log_output         # do log on output (default=True)
        self.list_path = None
        self.global_mean = None
        self.global_var = None
        self.cond_prob = None
        self.prior = None
        self._session = None
        self._graph = None
        self._meta_file = None
        self._checkpoint_folder = None

        # execute some init methods
        self._get_checkpoint_data(meta_file)
        self._create_session()
        self._create_graph()
        self._set_global_stats(stats_file)
        # setting transform matrix
        if self.transform:
            self._set_probabilities(cond_prob_file)

        # hint to produce a discrete output:
        # set transform_prob=False and log_output=False, then you get discrete labels out
        # of the inference model

    def do_inference(self, nj, input_folder, output_folder):
        # tmp dictionary
        inferenced_data = {}    # storing the inferenced data
        df_tmp = pd.DataFrame() # temp dataframe for accumulation data for calc mi

        dataset = DataIterator(nj, input_folder)
        misc = Misc()

        iterator = iter([i for i in range(1, dataset.get_size() + 1)])

        features_all = []
        phoneme_all = []

        while True:
            try:
                data_path = dataset.next_file()
                print(data_path)
                for key, mat in kaldi_io.read_mat_ark(data_path):
                    inferenced_data[key] = self._do_single_inference(mat[:, :39])  # not taking the phonemes in the data
                    if np.shape(mat)[1] > 39:   # get statistics for mi
                        phoneme_all.append(mat[:, 39])
                    features_all.append(self._normalize_data(mat[:, :39]))
                # if np.shape(df_tmp.values)[0] > 0:   # print mi if we accumulated data
                #     phoneme_all.append(df_tmp.values)
                #     # print('Mutual Information: ' + str(misc.calculate_mi(df_tmp.values[:, 0], df_tmp.values[:, 1])))
                #     df_tmp = pd.DataFrame()

                # print(labels_all)
                # print(phoneme_all)

                with open(output_folder + '/feats_vq_' + str(next(iterator)), 'wb') as f:
                    for key, mat in list(inferenced_data.items()):
                        if self.transform:
                            kaldi_io.write_mat(f, mat, key=key)
                        else:
                            kaldi_io.write_mat(f, mat[:, np.newaxis], key=key)
                inferenced_data = {}  # reset dict

            except StopIteration:
                # hardcoded for mi
                if False:
                    misc = Misc()
                    features_all = np.concatenate(features_all)
                    # print(features_all.shape)
                    # stats = {}
                    # stats['mean'] = np.expand_dims(np.mean(features_all[:, :39], axis=0), 1)
                    # stats['std'] = np.expand_dims(np.std(features_all[:, :39], axis=0), 1)
                    # with open('stats_new.mat', 'wb') as f:
                    #     for key, mat in list(stats.items()):
                    #         print(mat)
                    #         kaldi_io.write_mat(f, stats[key], key=key)

                    phoneme_all = np.expand_dims(np.concatenate(phoneme_all), 1)
                    phoneme_all = misc.trans_vec_to_phones(phoneme_all)
                    # print(misc.calculate_mi(features_all, phoneme_all))
                    mi, test_py, test_pw, test_pyw = self._session.run(["mutual_info:0", "p_y:0", "p_w:0", "p_yw:0"], feed_dict={"is_train:0": False,
                                                                        "ph_features:0": features_all,
                                                                        "ph_labels:0": phoneme_all})
                    print(mi)
                    tmp_pywtest = pd.DataFrame(test_py)
                    tmp_pywtest.to_csv('py_inf.txt', header=False, index=False)
                    tmp_pywtest = pd.DataFrame(test_pw)
                    tmp_pywtest.to_csv('pw_inf.txt', header=False, index=False)
                    tmp_pywtest = pd.DataFrame(test_pyw)
                    tmp_pywtest.to_csv('pwy_inf.txt', header=False, index=False)

                break

    def _do_single_inference(self, np_mat):
        # TODO check for None
        np_mat = self._normalize_data(np_mat)
        output = self._session.run("nn_output:0", feed_dict={"ph_features:0": np_mat, "is_train:0": False})
        # pd.DataFrame(self._session.run("fully_1/kernel:0")).to_csv('kernel_inf.txt', index=False, header=False)
        if self.transform:
            output = np.dot(output, self.cond_prob)
            # print(np.shape(output))
        else:
            output = np.argmax(output, axis=1)
            output = output.astype(np.float64, copy=False)

        if self.log_ouput:
            output /= self.prior    # divide through prior to get pseudo-likelihood
            output = np.log(output)
        return output

    def _create_session(self):
        self._session = tf.InteractiveSession()

    def _create_graph(self):
        saver = tf.train.import_meta_graph(self._checkpoint_folder + '/' + self._meta_file)
        saver.restore(self._session, tf.train.latest_checkpoint(self._checkpoint_folder))
        self._graph = tf.get_default_graph()

    def _create_list(self, folder_name):
        self.list_path = [folder_name + s for s in os.listdir(folder_name)]

        # sort list for later processing
        convert = lambda text: int(text) if text.isdigit() else text
        self.list_path.sort(key=lambda key: [convert(c) for c in re.split('([0-9]+)', key)])

    def _set_global_stats(self, file):
        for key, mat in kaldi_io.read_mat_ark(file):
            if key == 'mean':
                print('Setting mean')
                self.global_mean = np.transpose(mat)
            elif key == 'std':
                print('Setting var')
                self.global_var = np.transpose(mat)
            else:
                print('No mean or var set!!!')

    def _set_probabilities(self, file):
        # read in P(s_k|m_j) from training
        for key, mat in kaldi_io.read_mat_ark(file):
            if key == 'p_s_m':
                print('Setting P(s_k|m_j)')
                self.cond_prob = np.transpose(mat)  # we transpose for later dot product
            else:
                print('No probability found')

        # TODO hard coded for getting class counts
        for key, mat in kaldi_io.read_mat_ark('../class.counts'):
            if key == 'class_counts':
                print('Setting Prior')
                self.prior = mat / np.sum(mat)
            else:
                print('No Prior found')

    def _normalize_data(self, data_array):
        return (data_array - self.global_mean) / self.global_var

    def _get_checkpoint_data(self, checkpoint):
        assert type(checkpoint) == str

        # split string
        _, self._checkpoint_folder, self._meta_file = str.split(checkpoint, '/')
        self._checkpoint_folder = '../' + self._checkpoint_folder


if __name__ == "__main__":
    # set transform_prob=False if you don't want to get a continuous output (default is True)

    # flag for model type
    discrete = False

    if discrete:
        # discrete model
        model_discrete = TrainedModel('../model_checkpoint/saved_model-99.meta', '../stats_20k.mat',
                                      '../p_s_m.mat', log_output=False, transform_prob=False)

        model_discrete.do_inference(20, '/features/train_20k/feats', '/home/ga96yar/kaldi/egs/tedlium/s5_r2/'
                                                                     '/exp/test_400_0/vq_train')
        model_discrete.do_inference(30, 'test', '/home/ga96yar/kaldi/egs/tedlium/s5_r2/'
                                                'exp/test_400_0/vq_test')
    else:
        # continuous model
        model_continuous = TrainedModel('../model_checkpoint/saved_model-99.meta', '../stats_20k.mat',
                                        '../p_s_m.mat',)
        # model_continuous.do_inference(20, 'features/train_20k/feats', '../tmp/tmp_testing')
        model_continuous.do_inference(30, 'test', '../tmp/tmp_testing')







