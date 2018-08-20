


# path to data
path_train = 'tf_data/train_20k_state'
path_test = 'tf_data/test_state'
path_dev = 'tf_data/dev_state'

path_tensorboard = 'tensorboard'
path_checkpoint = 'model_checkpoint'
path_meta = 'meta_data'

# Hyperparameter
num_phonemes = 127
codebook_size = 400
batch_size = 15000
epoch_size = 100
dim_features = 39
dim_labels = 1

# Network parameter
scale_soft = 20.0
learning_rate = 1e-5
exponential_decay = False

# train Network
vqing = False
sampling_discrete = False
