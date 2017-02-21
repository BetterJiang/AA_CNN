#! /usr/bin/env python

import datetime
import os
import time

import tensorflow as tf

from datahelpers import data_helper_ml_mulmol6file as dh
from evaluators import eval_ml_mulmol_d as evaler
from networks.cnn_a_mulmol_2layer import TextCNN


# Training
def training(DO_DEV_SPLIT, FLAGS, scheme_name, vocabulary, embed_matrix, x_train, x_dev, y_train, y_dev,
             num_filters, dropout_prob, l2_lambda,
             pref2, pref3, suff2, suff3, pos,
             datah):
    with tf.Graph().as_default():
        session_conf = tf.ConfigProto(
            allow_soft_placement=FLAGS.allow_soft_placement,
            log_device_placement=FLAGS.log_device_placement)
        sess = tf.Session(config=session_conf)
        with sess.as_default():
            cnn = TextCNN(
                sequence_length=x_train.shape[1],
                num_classes=FLAGS.num_classes,  # Number of classification classes
                word_vocab_size=len(vocabulary),
                embedding_size=FLAGS.embedding_dim,
                filter_sizes=list(map(int, FLAGS.filter_sizes.split(","))),
                num_filters=num_filters,

                pref2_vocab_size=len(datah.p2_vocab),
                pref3_vocab_size=len(datah.p3_vocab),
                suff2_vocab_size=len(datah.s2_vocab),
                suff3_vocab_size=len(datah.s3_vocab),
                pos_vocab_size=len(datah.pos_vocab),

                l2_reg_lambda=l2_lambda,
                init_embedding=embed_matrix)

            # Define Training procedure
            global_step = tf.Variable(0, name="global_step", trainable=False)
            optimizer = tf.train.AdamOptimizer(1e-3)
            grads_and_vars = optimizer.compute_gradients(cnn.loss)
            train_op = optimizer.apply_gradients(grads_and_vars, global_step=global_step)

            # Keep track of gradient values and sparsity (optional)
            with tf.name_scope('grad_summary'):
                grad_summaries = []
                for g, v in grads_and_vars:
                    if g is not None:
                        grad_hist_summary = tf.histogram_summary("{}/grad/hist".format(v.name), g)
                        sparsity_summary = tf.scalar_summary("{}/grad/sparsity".format(v.name), tf.nn.zero_fraction(g))
                        grad_summaries.append(grad_hist_summary)
                        grad_summaries.append(sparsity_summary)
                grad_summaries_merged = tf.merge_summary(grad_summaries)

            # Output directory for models and summaries
            timestamp = str(int(time.time()))
            out_dir = os.path.abspath(os.path.join(os.path.curdir, "runs", scheme_name, timestamp))
            print("Writing to {}\n".format(out_dir))

            # Summaries for loss and accuracy
            loss_summary = tf.scalar_summary("loss", cnn.loss)
            # pred_ratio_summary = []
            # for i in range(FLAGS.num_classes):
            #     pred_ratio_summary.append(
            #         tf.scalar_summary("prediction/label_" + str(i) + "_percentage", cnn.rate_percentage[i]))
            acc_summary = tf.scalar_summary("accuracy", cnn.accuracy)

            # Train Summaries
            with tf.name_scope('train_summary'):
                train_summary_op = tf.merge_summary(
                    [loss_summary, acc_summary, grad_summaries_merged])
                train_summary_dir = os.path.join(out_dir, "summaries", "train")
                train_summary_writer = tf.train.SummaryWriter(train_summary_dir, sess.graph_def)

            # Dev summaries
            with tf.name_scope('dev_summary'):
                dev_summary_op = tf.merge_summary([loss_summary, acc_summary])
                dev_summary_dir = os.path.join(out_dir, "summaries", "dev")
                dev_summary_writer = tf.train.SummaryWriter(dev_summary_dir, sess.graph_def)

            # Checkpoint directory. Tensorflow assumes this directory already exists so we need to create it
            checkpoint_dir = os.path.abspath(os.path.join(out_dir, "checkpoints"))
            checkpoint_prefix = os.path.join(checkpoint_dir, "model")
            if not os.path.exists(checkpoint_dir):
                os.makedirs(checkpoint_dir)
            saver = tf.train.Saver(var_list=tf.all_variables(), max_to_keep=7)

            # Initialize all variables
            sess.run(tf.initialize_all_variables())

        def train_step(x_batch, y_batch, pref2_batch, pref3_batch, suff2_batch, suff3_batch, pos_batch):
            """
            A single training step
            """
            feed_dict = {
                cnn.input_x: x_batch,
                cnn.input_y: y_batch,

                cnn.input_pref2: pref2_batch,
                cnn.input_pref3: pref3_batch,
                cnn.input_suff2: suff2_batch,
                cnn.input_suff3: suff3_batch,
                cnn.input_pos: pos_batch,

                cnn.dropout_keep_prob: dropout_prob
            }
            _, step, summaries, loss, accuracy = sess.run(
                [train_op, global_step, train_summary_op, cnn.loss, cnn.accuracy],
                feed_dict)
            time_str = datetime.datetime.now().isoformat()
            print("{}: step {}, loss {:g}, acc {:g}".format(time_str, step, loss, accuracy))
            train_summary_writer.add_summary(summaries, step)

        def dev_step(x_batch, y_batch, writer=None):
            """
            Evaluates model on a dev set
            """
            feed_dict = {
                cnn.input_x: x_batch,
                cnn.input_y: y_batch,
                cnn.dropout_keep_prob: 1
            }
            step, summaries, loss, accuracy = sess.run(
                [global_step, dev_summary_op, cnn.loss, cnn.accuracy],
                feed_dict)
            time_str = datetime.datetime.now().isoformat()
            print("{}: step {}, loss {:g}, acc {:g}".format(time_str, step, loss, accuracy))
            if writer:
                writer.add_summary(summaries, step)

        # Generate batches
        batches = dh.DataHelper.batch_iter(list(zip(x_train, y_train, pref2, pref3, suff2, suff3, pos)), FLAGS.batch_size, FLAGS.num_epochs)
        # Training loop. For each batch...
        for batch in batches:
            x_batch, y_batch, pref2_batch, pref3_batch, suff2_batch, suff3_batch, pos_batch = zip(*batch)
            train_step(x_batch, y_batch, pref2_batch, pref3_batch, suff2_batch, suff3_batch, pos_batch)
            current_step = tf.train.global_step(sess, global_step)
            if DO_DEV_SPLIT and current_step % FLAGS.evaluate_every == 0:
                print("\nEvaluation:")
                dev_batches = dh.DataHelper.batch_iter(list(zip(x_dev, y_dev)), 100, 1)
                for dev_batch in dev_batches:
                    if len(dev_batch) > 0:
                        small_dev_x, small_dev_y = zip(*dev_batch)
                        dev_step(small_dev_x, small_dev_y, writer=dev_summary_writer)
                        print("")
            if current_step % FLAGS.checkpoint_every == 0:
                path = saver.save(sess, checkpoint_prefix, global_step=current_step)
                print("Saved model checkpoint to {}\n".format(path))
            if current_step == 30000:  # TODO: change here to stop training early... too short for prob I, need change
                break
    return timestamp

DO_DEV_SPLIT = False
small_step = [250, 500, 750, 1000]
bold_step = [2500, 3000, 3500, 4000, 4500]
small_step2 = [2000, 2250, 2500, 2750, 3000, 3250, 3500]


embed_dim = 100

o = dh.DataHelper(doc_level="sent")
output_file = open("100d_test_170206.txt", mode="aw")
dir_name = "ml_mulmol_res"

# Model Hyperparameters
tf.flags.DEFINE_integer("num_classes", o.num_of_classes, "Number of possible labels")

tf.flags.DEFINE_integer("embedding_dim", o.embedding_dim,
                        "Dimensionality of character embedding")
tf.flags.DEFINE_string("filter_sizes", "3,4,5", "Comma-separated filter sizes (default: '3,4,5')")  # TODO: filter size here, currently window size = 3,4,5
# tf.flags.DEFINE_integer("num_filters", 100, "Number of filters per filter size (default: 128)")
# tf.flags.DEFINE_float("dropout_keep_prob", 0.7, "Dropout keep probability (default: 0.5)")
# tf.flags.DEFINE_float("l2_reg_lambda", 0.1, "L2 regularizaion lambda (default: 0.0)")

# Training parameters
tf.flags.DEFINE_integer("batch_size", 64, "Batch Size (default: 64)")
tf.flags.DEFINE_integer("num_epochs", 200, "Number of training epochs (default: 200)")
tf.flags.DEFINE_integer("evaluate_every", 200, "Evaluate model on dev set after this many steps (default: 100)")
tf.flags.DEFINE_integer("checkpoint_every", 250, "Save model after this many steps (default: 100)")  # TODO change here for saving freq
# Misc Parameters
tf.flags.DEFINE_boolean("allow_soft_placement", True, "Allow device soft device placement")
tf.flags.DEFINE_boolean("log_device_placement", False, "Log placement of ops on devices")

FLAGS = tf.flags.FLAGS
FLAGS._parse_flags()
print("\nParameters:")
for attr, value in sorted(FLAGS.__flags.items()):
    print("{}={}".format(attr.upper(), value))
print("")


[x_train, pos_train, wl_train, p2_train, p3_train, s2_train, s3_train, labels_train, vocab, vocab_inv, embed_matrix]\
    = o.load_data()
[x_test, pos_test, wl_test, p2_test, p3_test, s2_test, s3_test, labels_test, _, _, doc_size_test] = o.load_test_data()

ev = evaler.evaler()
ev.load(o)

for f_size in [100]:  # TODO: add number here for multiple filter count test, when 100 we generate 300 per sentence ()
    for l2 in [0.1]:  # TODO: L2 regularization here
        for drop in [0.75]:  # TODO: drop out keep rate here

            print("===== Filter Size: "+str(f_size)+"\n")
            print("===== L2 Norm: "+str(l2)+"\n")
            print("===== Drop Out: "+str(drop)+"\n\n\n")

            ts = training(DO_DEV_SPLIT, FLAGS, dir_name, vocab, embed_matrix, x_train, x_test, labels_train, labels_test,
                          f_size, drop, l2,
                          p2_train, p3_train, s2_train, s3_train, pos_train,
                          o)

            #for train_step in small_step2:
            checkpoint_dir = "./runs/" + dir_name + "/" + str(ts) + "/checkpoints/"
            ev.test(checkpoint_dir, 30000, output_file, documentAcc=True)

#output_file.close()