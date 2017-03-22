from timeit import default_timer as timer
from datahelpers import data_helper_ml_mulmol6_Read as dh6
from datahelpers import data_helper_ml_normal as dh
from trainer import TrainTask as tr
from evaluators import eval_ml_mulmol_d as evaler
from evaluators import eval_ml_origin as evaler_one


if __name__ == "__main__":

    input_component = "OneChannel"

    if input_component == "OneChannel":
        dater = dh.DataHelper(doc_level="sent", train_holdout=0.80, embed_type="glove", embed_dim=300)
        ev = evaler_one.evaler()
    elif input_component == "SixChannel":
        dater = dh6.DataHelperMulMol6(doc_level="sent", train_holdout=0.80)
        ev = evaler.evaler()
    else:
        raise NotImplementedError

    ###############################################
    # exp_names you can choose from at this point:
    #
    # Input Components:
    #
    # *OneChannel
    # *SixChannel
    #
    # Middle Components:
    #
    # *NParallelConvOnePoolNFC
    # *YifanConv
    # *ParallelJoinedConv
    # *NCrossSizeParallelConvNFC
    ################################################
    tt = tr.TrainTask(data_helper=dater, input_component=input_component, exp_name="NCrossSizeParallelConvNFC",
                      filter_sizes=[[3, 4, 5], [3, 4, 5]], batch_size=64, dataset="ML", evaluate_every=5000, checkpoint_every=5000)
    start = timer()
    # n_fc variable controls how many fc layers you got at the end, n_conv does that for conv layers

    ts = tt.training(num_filters=100, dropout_keep_prob=0.7, n_steps=100000, l2_lambda=0.1, dropout=True,
                batch_normalize=False, elu=False, n_conv=2, fc=[])
    end = timer()
    print(end - start)

    ev.load(dater)
    with open(tt.exp_name + ".txt", mode="aw") as of:
        checkpoint_dir = tt.exp_dir + str(ts) + "/checkpoints/"
        ev.test(checkpoint_dir, None, of, documentAcc=True)
