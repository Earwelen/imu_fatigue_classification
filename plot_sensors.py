# #######################################################################
# Imports
import logging
import os
import numpy as np
import pandas as pd
from tqdm import tqdm

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import label
from matplotlib import pyplot as plt
from matplotlib import patches as mpatches
from scipy import fftpack
from scipy.signal import blackman
from pprint import pprint



# #######################################################################
# #######################       Parameters        #######################
# #######################################################################
DEBUG = 1
SKIP_BEG_SEC = 1        # remove what happens when the recording on the smartphone is started and put into pocket
SKIP_END_SEC = 1        # same, for the end, when removed from pocket
SKIP_CHANGE_SEC = 0.8     # same, between transitions
THRESHOLD = 1         # threshold to cut the data
LABELS = {"none": -1, "standing": 0,
          "walk_rested": 1, "walk_tired": 2, "walk_very_tired": 3}

# Holders:
all_frames = []
frequencies = []
freq = 0

# Setup
col_to_plot = {1: ["acc_x", "acc_y", "acc_z"],
               2: ["acc_derivative_x", "acc_derivative_y", "acc_derivative_z"],
               3: ["acc_sum", "acc_sum_smoth"],
               4: ["acc_tot", "acc_deriv_tot"],
               5: ["gyro_x", "gyro_y", "gyro_z"]}

col_to_fft = col_to_plot[1] + col_to_plot[2] + col_to_plot[3] + col_to_plot[4] + col_to_plot[5]


# #######################################################################
# #######################         load CSV        #######################
# #######################################################################
def load_csv(file_name):
    # Get read of first line (sep=;) when reading the csv file
    data = pd.read_csv(file_name, sep=";", skiprows=1, index_col=None)
    data["labels"] = LABELS["none"]
    return data


# #######################################################################
# #######################       main function     #######################
# #######################################################################
def clean_data(data, tiredness_state):
    # Set the datetime as index
    data.date_time = pd.to_datetime(data["date_time"], format='%Y-%m-%d %H:%M:%S:%f')
    # data["index"] = range(data.shape[0])
    # data.set_index("index")
    # time_ms converted into seconds
    data.time_ms = data.time_ms / 1000
    # find total time, sampling frequency
    logging.debug(f'starts at {data["date_time"][0]}, ends at {data["date_time"].iloc[-1]}')
    total_time = (data["date_time"].iloc[-1] - data["date_time"][0])
    frequency = int(round(len(data) / total_time.seconds, 0))
    logging.debug(len(data))
    logging.debug(frequency)


    # #######################################################################
    # #####################       PRINT AND PLOT       ######################
    # #######################################################################
    logging.info("Printing section")
    # Print some stuff
    if DEBUG > 6:
        print(data.head())
        print(data.columns)
        print(data.dtypes)


    # Plotting
    if DEBUG > 7:
        columns = ["acc_x", "acc_y", "acc_z", "grav_x", "grav_y", "grav_z",
                   "lin_acc_x", "lin_acc_y", "lin_acc_z",
                   "gyro_x", "gyro_y", "gyro_z",
                   "mag_x", "mag_y", "mag_z", "sound_lvl", ]
        col_to_plot = ["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z", "mag_x", "mag_y", "mag_z", ]
        plt.figure(f"{index}- ROW data")
        plt.plot(data.time_ms, data[col_to_plot])
        plt.legend(col_to_plot)
        plt.tight_layout()
        plt.show()



    # #######################################################################
    # #######################         FEATURES        #######################
    # #######################################################################
    logging.info("Feature engineering section")

    # window filter
    # add each difference on a 0.2 sec window
    # if that sum of noise is low, cut before, define it as standing state.
    # If DEBUG
    if DEBUG > 3:
        plt.figure(f"{index}- Smooth and acc variation")

    # Smoothing each acc axis
    axis = ('x', 'y', 'z')
    for xyz in axis:
        acc_smooth_xyz = f"acc_smooth_{xyz}"
        acc_derivative_xyz = f"acc_derivative_{xyz}"
        # Smooth acc on xyz axis
        data[acc_smooth_xyz] = data[f"acc_{xyz}"].rolling(round(0.2*frequency), win_type="hamming", center=True).sum()
        # compute derivative of each axis
        data[acc_derivative_xyz] = abs(data[acc_smooth_xyz].shift(1) - data[acc_smooth_xyz].shift(-1))
        if DEBUG > 5:
            plt.plot(data.time_ms, data[acc_smooth_xyz], label=acc_smooth_xyz)

    # sum of derivatives of each axis
    data["acc_tot"] = list(np.sqrt(data["acc_x"]**2 + data["acc_y"]**2 + data["acc_z"]**2))
    data["acc_deriv_tot"] = list(np.sqrt(data["acc_derivative_x"]**2 + data["acc_derivative_y"]**2 + data["acc_derivative_z"]**2))

    data["acc_sum"] = data["acc_derivative_x"] + data["acc_derivative_y"] + data["acc_derivative_z"]
    data["acc_sum_smoth"] = data["acc_sum"].rolling(round(0.8*frequency), win_type="hamming", center=True).sum() \
                            * 2 / round(0.8*frequency)


    # If DEBUG
    if DEBUG > 3:
        # plt.plot(data.time_ms, data["acc_sum"], label="acc_sum")
        plt.plot(data.time_ms, data["acc_sum_smoth"], label="acc_sum_smoth")
        plt.tight_layout()
        plt.legend()
        plt.show()

    #
    # ##################################################################
    # skip beginning and end of files
    # Labels
    # ##################################################################
    data.drop(range(SKIP_BEG_SEC*frequency), inplace=True)
    data.index = range(data.shape[0])

    # Ensure that we found the resting state
    i0_set_rest = data[data["acc_sum_smoth"] < THRESHOLD].index[0]
    data.drop(data.index[range(i0_set_rest)], inplace=True)      # remove beginning with noise
    data.index = range(data.shape[0])
    i0_set_rest = 0
    # Label until the end of first rest
    i1_rest_walk = data.loc[data.index > i0_set_rest + SKIP_CHANGE_SEC*frequency, "acc_sum_smoth"][data["acc_sum_smoth"] > THRESHOLD].index[0]
    data.loc[data.index <= i1_rest_walk, "labels"] = LABELS["standing"]
    # Label until the end of first walking
    i2_walk_rest = data.loc[data.index > i1_rest_walk + SKIP_CHANGE_SEC*frequency, "acc_sum_smoth"][data["acc_sum_smoth"] < THRESHOLD].index[0]
    data.loc[(i1_rest_walk <= data.index) & (data.index < i2_walk_rest), "labels"] = LABELS[tiredness_state]
    # Label until the turn
    i3_rest_turn = data.loc[data.index > i2_walk_rest + SKIP_CHANGE_SEC*frequency, "acc_sum_smoth"][data["acc_sum_smoth"] > THRESHOLD].index[0]
    data.loc[(i2_walk_rest <= data.index) & (data.index < i3_rest_turn), "labels"] = LABELS["standing"]
    # Label until rest
    i4_turn_rest = data.loc[data.index > i3_rest_turn + SKIP_CHANGE_SEC*frequency, "acc_sum_smoth"][data["acc_sum_smoth"] < THRESHOLD].index[0]
    data.loc[(i3_rest_turn <= data.index) & (data.index < i4_turn_rest), "labels"] = LABELS["none"]
    # Label until 2nd walk
    i5_rest_walk = data.loc[data.index > i4_turn_rest + SKIP_CHANGE_SEC*frequency, "acc_sum_smoth"][data["acc_sum_smoth"] > THRESHOLD].index[0]
    data.loc[(i4_turn_rest <= data.index) & (data.index < i5_rest_walk), "labels"] = LABELS["standing"]
    # Label until 2nd rest
    i6_walk_rest = data.loc[data.index > i5_rest_walk + SKIP_CHANGE_SEC*frequency, "acc_sum_smoth"][data["acc_sum_smoth"] < THRESHOLD].index[0]
    data.loc[(i5_rest_walk <= data.index) & (data.index < i6_walk_rest), "labels"] = LABELS[tiredness_state]
    # Label until noise
    i7_rest_noise = data.loc[data.index > i6_walk_rest + SKIP_CHANGE_SEC*frequency, "acc_sum_smoth"][data["acc_sum_smoth"] > THRESHOLD].index[0] - 10
    data.loc[(i6_walk_rest <= data.index) & (data.index < i7_rest_noise), "labels"] = LABELS["standing"]
    # Drop end part
    data.drop(data.loc[(i7_rest_noise <= data.index)].index, inplace=True)

    # Collect indexes
    split_indexes = [i0_set_rest, i1_rest_walk, i2_walk_rest, i3_rest_turn, i4_turn_rest,
                     i5_rest_walk, i6_walk_rest, i7_rest_noise]

    if DEBUG > 2:
        print(split_indexes)
    if DEBUG > 5:
        print(data["labels"].sample(10))

    # Plots
    if DEBUG > 2 and index in (3, 14):
        plt.figure(f"{index}- Gyro and labels")
        # plt.plot(data.time_ms, data["acc_sum"], label="acc_sum")
        plt.plot(data.time_ms, data["gyro_x"], label="acc_sum")
        plt.plot(data.time_ms, data["gyro_y"], label="acc_sum")
        plt.plot(data.time_ms, data["gyro_z"], label="acc_sum")
        # plt.plot(data.time_ms, data["acc_sum_smoth"], label="acc_sum_smoth")
        plt.plot(data.time_ms, data["labels"], label="labels")
        plt.tight_layout()
        plt.legend()
        # plt.show()

    #
    # Split each part rest / walk / tired_walk ...
    split_frame = []
    window = frequency * 4

    for ind_low, ind_high in zip(split_indexes[:-1], split_indexes[1:]):

        # Chop in smaller windows of 4 seconds for walking labels
        if data["labels"].iloc[ind_low] == LABELS[tiredness_state]:
            n = 0
            while ind_low + (n+1) * window < ind_high:
                chop_low = ind_low + n * window
                chop_high = ind_low + (n+1) * window
                split_frame.append({"label": data["labels"].iloc[chop_low],
                                    "frame": data[(chop_low <= data.index) & (data.index < chop_high)]})
                n += 1

        # normal labels are not chopped
        else:
            split_frame.append({"label": data["labels"].iloc[ind_low],
                                "frame": data[(ind_low <= data.index) & (data.index < ind_high)]})

        if DEBUG > 6:
            print("ind low and high : ", ind_low, ind_high, data.shape)
            print(data["labels"].iloc[ind_low])

    return split_frame, frequency


# #######################################################################
# #######################          KERAS          #######################
# #######################################################################
if False:
    import keras
    from keras.layers import GRU, Dense
    from keras.models import Sequential
    x = (nb_of_data, nb_of_samples, nb_of_features)
    y = nb_of_data * 1

    model = Sequential(input_shape={timesteps, n_features})
    model.add(GRU(256))
    model.add(Dense(1))

    model.compile(optimizer='adam')

    model.fit(x, y)


# #######################################################################
# #######################          SETUP          #######################
# #######################################################################
def setup_files():
    # Logging Settings
    logging.basicConfig()
    logging.info("Setup section")

    # Folder and Files
    folder = "D:/Drive/Singapore/Courses/CS6206-HCI Human Computer Interaction/Project/Data"
    os.chdir(folder)
    files = [f for f in os.listdir(folder) if f.endswith(".csv")]
    logging.info(f"found {len(files)} files in folder {folder}")

    return files


# #######################################################################
# #######################          MAIN           #######################
# #######################################################################
def files_load_clean_to_feat(files):
    global all_frames
    global THRESHOLD

    for index, file_name in tqdm(enumerate(files), total=len(files)):

        if index not in (20,):
            # Fixing early experiments
            if index == 0:              THRESHOLD = 5.67
            elif index == 3:            THRESHOLD = 3.5
            elif index in range(5):     THRESHOLD = 4
            else:                       THRESHOLD = 2

            # if index in (0, 3): DEBUG = 4
            # else:  DEBUG = 0

            state = "none"
            if index in range(0, 6):      state = "walk_rested"
            elif index in range(6, 12):   state = "walk_tired"
            elif index in range(12, 18):  state = "walk_very_tired"

            frame = load_csv(file_name)
            split_frame, frequency = clean_data(frame, state)
            if DEBUG > 2:
                print(f"\n *** File number {index} ***")
                print(frame.shape)

            all_frames.extend(split_frame)
            frequencies.append(frequency)

    global freq
    freq = sum(frequencies) / len(frequencies)


def plot_stuff():
    # whyyyyyy is plt. blocking...

    print("\n")
    print("Preprocessing done, continuing on single dataset extraction")
    print("len(all_frames)", len(all_frames))
    # pprint(all_frames)


    # Compute fft on all subsets
    col_to_plot = ["acc_derivative_z",]

    plt.figure(f"FFT comparison {col_to_plot}")
    plt.xlabel('Frequency in Hertz [Hz]')
    plt.ylabel('Frequency Domain Magnitude (Spectrum)')
    plt.xlim([-0.2, 10])
    red_patch = mpatches.Patch(color='red', label='walk_very_tired')
    green_patch = mpatches.Patch(color='green', label='walk_rested')
    blue_patch = mpatches.Patch(color='blue', label='standing')
    plt.legend(handles=[red_patch, green_patch, blue_patch])

    plt.show()
    plt.close("all")


def fft_frames():
    print("Compute the fft for some columns")

    for index, dat in tqdm(enumerate(all_frames), total=len(all_frames)):

        if dat["label"] != LABELS["none"]:      # and dat["label"] != LABELS["walk_tired"]

            # Find the state
            state = list(LABELS.keys())[list(LABELS.values()).index(dat['label'])]

            for column in col_to_fft:

                signal = dat["frame"][column]
                w = blackman(len(signal))

                X = fftpack.fft(signal * w)
                # todo try without the window

                dat["frame"][f"fft_{column}"] = X

                if DEBUG > 2:
                    if state == "standing":             colour = 'b'
                    elif state == "walk_rested":        colour = 'g'
                    elif state == "walk_very_tired":    colour = 'r'
                    else:                               colour = 'y'
                    freqs = fftpack.fftfreq(len(signal)) * freq
                    plt.plot(freqs, abs(X), colour)

    print("Done")


def plot_fft(frame_id):
    if all_frames[frame_id]['label'] < 0:
        print("Frame to drop, not classified")
        return
    print("********************************************")
    print(f"Label = {all_frames[frame_id]['label']}")
    print(f"Columns: {all_frames[frame_id]['frame'].columns}")
    signal = all_frames[frame_id]['frame']['fft_acc_sum_smoth']
    N = len(signal)
    T = 1.0 / freq
    xf = np.linspace(0.0, 1.0 / (2.0 * T), N // 10)
    yf = signal
    plt.plot(xf, (2.0 / N / 10.0) * np.abs(yf[0:N // 10]))
    plt.grid()
    plt.show()


def print_values(frame_id):
    print(f"Label is {all_frames[frame_id]['label']}")
    print(np.abs(all_frames[frame_id]['frame']['fft_acc_sum_smoth'][:10]))


def features_to_pandas():

    columns = ['label', ] + [f['frame'][col][:5] for col in col_to_fft] # todo
    data = []
    for f in tqdm(all_frames, total=len(all_frames)):

        sample = [f['label'], ] + [f['frame'][col][:5] for col in col_to_fft] # todo into different columns

        data.append(sample)

    features = pd.DataFrame.from_records(data, columns=columns)
    return features


# #######################################################################
# #######################         sklearn         #######################
# #######################################################################
def classification():
    logging.info("sklearn section")

    # todo feed into random forest
    if False:
        rf = RandomForestClassifier(n_estimators=100)
        rf.fit(x, y)
        rf.predict()






































