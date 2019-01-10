from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
import object_detection
from google.protobuf import text_format
from object_detection import exporter
from object_detection.protos import pipeline_pb2
from object_detection import model_lib
import argparse
import fnmatch
import os, re

parser = argparse.ArgumentParser("""This module can automatically train multiple models on a single dataset, 
it searches for any folder in the model directory supplied and then uses the .config file inside to train
the model, it will automatically find the most recent ckpt file and use it for training.""" )
parser.add_argument("--model_dir", help="The directory containing the model folders for your session", type=str, default="./models")
parser.add_argument("--output_dir", help="The directory in each of the model folders to store the training results", type=str, default="./training")
parser.add_argument("training_data", help="Directory containing the tfrecords", type=str)
parser.add_argument("--export_inference", help="Set this to true to export a frozen inference graph after training", action="store_true", default=False)
parser.add_argument("-i", "--iterations", help="The training iterations for each model", type=int, default=50000)
args = parser.parse_args()

def find_file_matching_pattern(path, pattern, min_match_count=1):
	"""Finds the first valid file in a directory that
	matches the given pattern using fnmatch, but only
	if the number of matches if above or at min_match_count"""
	matches = list(fnmatch.filter(os.listdir(path), pattern))
	return matches[0] if len(matches) > 0 else None

def retrieve_model_list():
	"""Finds all valid directories in the given model directory
	and returns a list containing them all"""

	model_list = []
	for f in os.listdir(args.model_dir):
		path = os.path.join(args.model_dir, f)
		if os.path.is_dir(path):
			if find_file_matching_pattern(path, "*.config"):
				if find_file_matching_pattern(path, "model.ckpt*", 3):
					model_list.append(path)
				else:
					print('Skipping: {} does not contain model.ckpt files'.format(path))
			else:
				print('Skipping: {} does not contain .config file'.format(path))
		else:
			print('Skipping: {} is not a valid folder'.format(f))

	return model_list

def create_output_dirs(model_list):
	"""Creates the output training directories for each of the given models"""

	for m in model_list:
		os.mkdir(os.path.join(m, args.output_dir))

def find_ckpt_prefix(model_path):
	"""Finds the highest ckpt prefix of the ckpt files
	in the model's directory"""
	ckpt_list = fnmatch.filter(os.listdir(model_path), "model.ckpt-*")
	response_string = "model.ckpt"
	if len(ckpt_list) > 0:
		number = max(map(lambda x: int(re.findall('\d+', x)[0]), ckpt_list))
		response_string += "-" + str(number)
	return response_string

def create_inference_graph(model_path):
	"""Exports a models training progress as a path"""

	pipeline_config = pipeline_pb2.TrainEvalPipelineConfig()
	with tf.gfile.GFile(os.path.join(model_path, '*.config'), 'r') as f:
		text_format.Merge(f.read(), pipeline_config)
	text_format.Merge('', pipeline_config)
	exporter.export_inference_graph(
		"image_tensor", pipeline_config, find_ckpt_prefix(model_path),
		os.path.join(model_path, args.output_dir), input_shape=None,
		write_inference_graph=False)

def train_model(model_path):
	"""Trains a model using the default parameters"""

	config = tf.estimator.RunConfig(model_dir=model_path)

	train_and_eval_dict = model_lib.create_estimator_and_inputs(
		run_config=config,
		hparams=model_hparams.create_hparams(None),
		pipeline_config_path=os.path.join(model_path, find_file_matching_pattern(model_path, "*.config")),
		train_steps=args.iterations,
		sample_1_of_n_eval_examples=1,
		sample_1_of_n_eval_on_train_examples=(5))
	estimator = train_and_eval_dict['estimator']
	train_input_fn = train_and_eval_dict['train_input_fn']
	eval_input_fns = train_and_eval_dict['eval_input_fns']
	eval_on_train_input_fn = train_and_eval_dict['eval_on_train_input_fn']
	predict_input_fn = train_and_eval_dict['predict_input_fn']
	train_steps = train_and_eval_dict['train_steps']

	train_spec, eval_specs = model_lib.create_train_and_eval_specs(
		train_input_fn,
		eval_input_fns,
		eval_on_train_input_fn,
		predict_input_fn,
		train_steps,
		eval_on_train_data=False)

	# Currently only a single Eval Spec is allowed.
	tf.estimator.train_and_evaluate(estimator, train_spec, eval_specs[0])

if __name__ == "__main__":
	print('Finding models')
	model_list = retrieve_model_list()
	print('Creating output directories')
	create_output_dirs(model_list)
	for m in model_list:
		print('Training {}'.format(m))
		train_model(m)
		if args.export_inference:
			print('Exporting inference graph')
			create_inference_graph(m)


























