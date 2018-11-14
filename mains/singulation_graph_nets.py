import tensorflow as tf

from data_loader.data_generator import DataGenerator
from trainers.singulation_trainer import SingulationTrainer
from utils.config import process_config
from utils.dirs import create_dirs
from utils.logger import Logger
from utils.utils import get_args
from models.singulation_models import EncodeProcessDecode


def main():
    # capture the config path from the run arguments
    # then process the json configuration file
    try:
        args = get_args()
        config = process_config(args.config)

    except:
        print("missing or invalid arguments")
        exit(0)

    # create the experiments dirs
    create_dirs([config.summary_dir, config.checkpoint_dir])

    # create tensorflow session
    sess = tf.Session()

    # create your data generator
    train_data = DataGenerator(config, sess, train=True)
    valid_data = DataGenerator(config, sess, train=False)

    model = EncodeProcessDecode(config)

    # create tensorboard logger
    logger = Logger(sess, config)

    # create trainer and pass all the previous components to it
    trainer = SingulationTrainer(sess, model, train_data, valid_data, config, logger)

    # load model if exists
    model.load(sess)

    trainer.train()

if __name__ == '__main__':
    main()