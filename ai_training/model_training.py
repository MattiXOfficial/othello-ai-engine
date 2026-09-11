"""
Module for training Machine Learning and Deep Learning models for Othello.
"""

import os
import ast

import pandas as pa
import numpy as np
import joblib

import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from sklearn.model_selection import learning_curve, StratifiedKFold

from keras.models import Model
from keras.layers import (
    Dense,
    Conv2D,
    Input,
    BatchNormalization,
    Dropout,
    GlobalMaxPooling2D,
)
from keras.optimizers import Adam
from keras.callbacks import EarlyStopping, ReduceLROnPlateau


class ModelLearning:
    """
    Class managing the training of ML and DL models.
    """

    def __init__(self):
        # n_estimators=40: A compromise to reduce size
        # max_leaf_nodes=25000: Strict limit to retain excellent
        # accuracy while keeping the file < 200 MB
        # n_jobs=-1: Uses all processor cores to speed up
        # training
        # random_state=42: the seed of the random number generator
        self.model = RandomForestClassifier(
            n_estimators=40,
            max_leaf_nodes=25000,
            n_jobs=-1,
            random_state=42,
        )

    def learn_model(self):
        """
        Trains and saves a RandomForestClassifier model.
        """
        dataset_path = os.path.join(
            os.path.dirname(__file__), "othello_dataset_formatted_flat.csv"
        )
        print("Loading data...")
        dataset = pa.read_csv(dataset_path)

        # Separate features (board) and target (winner)
        x_features = dataset.drop(columns=["winner", "board_size"])
        y = dataset["winner"].replace(-1, 0)

        # Split into training (80%) and test (20%) sets
        x_train, x_test, y_train, y_test = train_test_split(
            x_features, y, test_size=0.2, random_state=42
        )

        print("Training RandomForestClassifier model...")
        self.model.fit(x_train, y_train)

        print("Evaluating model...")
        y_pred_test = self.model.predict(x_test)
        y_pred_train = self.model.predict(x_train)

        accuracy_test = accuracy_score(y_test, y_pred_test)
        accuracy_train = accuracy_score(y_train, y_pred_train)

        print(f"Accuracy on test set: " f"{accuracy_test * 100:.2f}%")
        print(f"Accuracy on train set: " f"{accuracy_train * 100:.2f}%")

        # Save the model
        model_save_path = os.path.join(
            os.path.dirname(__file__), "random_forest_model.pkl"
        )
        joblib.dump(self.model, model_save_path)
        print(f"Model saved to: {model_save_path}")

        # --- GENERATE LEARNING CURVE (SCIKIT-LEARN) ---
        print("Generating learning curve (this might take a moment)...")

        # Create a cross-validation strategy that SHUFFLES the data
        # random_state=42 ensures the shuffle is always exactly the same
        cv_strategy = StratifiedKFold(
            n_splits=5, shuffle=True, random_state=42
        )

        # Test model on 5 different dataset sizes (from 20% to 100%)
        # Uses cv_strategy instead of cv=5
        train_sizes, train_scores, test_scores = learning_curve(
            self.model,
            x_features,
            y,
            cv=cv_strategy,
            n_jobs=-1,
            train_sizes=np.linspace(0.2, 1.0, 5),
            scoring="accuracy",
        )

        # Calculate means and standard deviations to plot shaded areas
        train_scores_mean = np.mean(train_scores, axis=1)
        train_scores_std = np.std(train_scores, axis=1)
        test_scores_mean = np.mean(test_scores, axis=1)
        test_scores_std = np.std(test_scores, axis=1)

        # Create plot
        plt.figure(figsize=(10, 6))
        plt.title(
            "Learning Curve - RandomForest (Shuffled Data)",
            fontsize=14,
        )
        plt.xlabel("Number of training examples", fontsize=12)
        plt.ylabel("Accuracy", fontsize=12)
        plt.grid(True, linestyle="--", alpha=0.7)

        # Shaded area (variance) and line for training
        plt.fill_between(
            train_sizes,
            train_scores_mean - train_scores_std,
            train_scores_mean + train_scores_std,
            alpha=0.1,
            color="blue",
        )
        plt.plot(
            train_sizes,
            train_scores_mean,
            "o-",
            color="blue",
            linewidth=2,
            label="Training (Train)",
        )

        # Shaded area (variance) and line for validation
        plt.fill_between(
            train_sizes,
            test_scores_mean - test_scores_std,
            test_scores_mean + test_scores_std,
            alpha=0.1,
            color="orange",
        )
        plt.plot(
            train_sizes,
            test_scores_mean,
            "o-",
            color="orange",
            linewidth=2,
            label="Validation (Cross-val)",
        )

        plt.legend(loc="lower right", fontsize=12)
        plt.tight_layout()

        # Save image
        plot_save_path = os.path.join(
            os.path.dirname(__file__), "rf_learning_curve.png"
        )
        plt.savefig(plot_save_path)
        print(f"Learning curve saved to: {plot_save_path}")

        # Display on screen
        plt.show()

    def deep_learning_cnn(self):
        """
        Trains and saves a Convolutional Neural Network (CNN) model.
        """
        dataset_path = os.path.join(
            os.path.dirname(__file__), "othello_dataset_formatted_2d.csv"
        )
        print("Loading data...")

        dataset_cnn = pa.read_csv(dataset_path, engine="python")
        dataset_cnn = dataset_cnn[dataset_cnn["winner"] != 0]

        dataset_cnn["board_grid"] = dataset_cnn["board_grid"].apply(
            ast.literal_eval
        )

        x_features = np.stack(dataset_cnn["board_grid"].values).astype(
            np.float32
        )

        y = dataset_cnn["winner"].replace(-1, 0).values

        # Split into training (80%) and test (20%) sets
        x_train, x_test, y_train, y_test = train_test_split(
            x_features, y, test_size=0.2, random_state=42
        )

        inputs = Input(shape=(None, None, 1))

        # Block 1
        x = Conv2D(128, kernel_size=(3, 3), activation="relu", padding="same")(
            inputs
        )
        x = BatchNormalization()(x)

        # Block 2
        x = Conv2D(256, kernel_size=(3, 3), activation="relu", padding="same")(
            x
        )
        x = BatchNormalization()(x)

        # Block 3
        x = Conv2D(256, kernel_size=(3, 3), activation="relu", padding="same")(
            x
        )
        x = BatchNormalization()(x)

        # Block 4
        x = Conv2D(512, kernel_size=(3, 3), activation="relu", padding="same")(
            x
        )
        x = BatchNormalization()(x)

        x = GlobalMaxPooling2D()(x)

        # Dense layers with Dropout to prevent overfitting
        x = Dense(512, activation="relu")(x)
        x = Dropout(0.5)(x)
        x = Dense(128, activation="relu")(x)
        x = Dropout(0.5)(x)

        # Final output (1 possible result (black or white) so 1 neuron)
        outputs = Dense(1, activation="sigmoid")(x)

        model_cnn = Model(inputs=inputs, outputs=outputs)

        optimizer = Adam(learning_rate=0.001)
        # loss="binary_crossentropy": Standard loss function for evaluating
        # errors in binary classification tasks.
        model_cnn.compile(
            optimizer=optimizer,
            loss="binary_crossentropy",
            metrics=["accuracy"],
        )

        # ReduceLROnPlateau: Decreases learning rate if accuracy plateaus
        lr_scheduler = ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=2, verbose=1
        )
        # EarlyStopping: Stops training if the model starts to overfit
        early_stopping = EarlyStopping(
            monitor="val_loss",
            patience=4,
            restore_best_weights=True,
            verbose=1,
        )

        # batch_size=256: Scaled up to speed up Python execution loops and
        # better vectorize the CPU math.
        # epochs=10: Reduced epochs to prevent excessively long training
        # time wait.
        history = model_cnn.fit(
            x_train,
            y_train,
            epochs=40,
            batch_size=512,
            validation_data=(x_test, y_test),
            callbacks=[lr_scheduler, early_stopping],
        )

        model_save_path_cnn = os.path.join(
            os.path.dirname(__file__), "cnn_model.keras"
        )
        model_cnn.save(model_save_path_cnn)
        print(f"CNN model saved to: {model_save_path_cnn}")

        score_cnn = model_cnn.evaluate(x_test, y_test, verbose=0)
        print("Test accuracy (CNN):", score_cnn[1])

        # --- DISPLAY LEARNING CURVES ---
        plt.figure(figsize=(14, 5))

        # 1st plot: Accuracy
        plt.subplot(1, 2, 1)
        plt.plot(
            history.history["accuracy"],
            label="Training (Train)",
            linewidth=2,
        )
        plt.plot(
            history.history["val_accuracy"],
            label="Validation (Test)",
            linewidth=2,
        )
        plt.title("Accuracy Evolution", fontsize=14)
        plt.xlabel("Epochs", fontsize=12)
        plt.ylabel("Accuracy", fontsize=12)
        plt.legend(fontsize=12)
        plt.grid(True, linestyle="--", alpha=0.7)

        # 2nd plot: Loss
        plt.subplot(1, 2, 2)
        plt.plot(
            history.history["loss"], label="Training (Train)", linewidth=2
        )
        plt.plot(
            history.history["val_loss"], label="Validation (Test)", linewidth=2
        )
        plt.title("Loss Evolution", fontsize=14)
        plt.xlabel("Epochs", fontsize=12)
        plt.ylabel("Loss", fontsize=12)
        plt.legend(fontsize=12)
        plt.grid(True, linestyle="--", alpha=0.7)

        plt.tight_layout()

        # Save image for report
        plot_path = os.path.join(
            os.path.dirname(__file__), "learning_curves.png"
        )
        plt.savefig(plot_path)
        print(f"Learning curves saved to: {plot_path}")

        # Display on screen
        plt.show()


if __name__ == "__main__":
    main_learning = ModelLearning()
    main_learning.learn_model()
    # main_learning.deep_learning_cnn()
