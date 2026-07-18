# Fleet Pulse — one command per pipeline stage.
# Stage DAG: data -> features -> train -> app   (ADF would schedule these same stages)

VENV := .venv/bin
export JAVA_HOME := /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PYSPARK_PYTHON := $(CURDIR)/$(VENV)/python
export PYSPARK_DRIVER_PYTHON := $(CURDIR)/$(VENV)/python
export PYTHONPATH := $(CURDIR)/src

.PHONY: setup data features train app test sample all

setup:
	python3.13 -m venv .venv
	$(VENV)/pip install --upgrade pip
	$(VENV)/pip install -r requirements.txt

data:            ## generate the synthetic fleet (raw parquet)
	$(VENV)/python -m fleetgen.generate --config config/fleet_config.yaml

features:        ## PySpark feature engineering + leakage-safe labels
	$(VENV)/python src/pipeline/features_spark.py
	$(VENV)/python src/pipeline/labels.py

train:           ## train + evaluate models, write artifacts for the app
	$(VENV)/python src/models/train_xgb.py
	$(VENV)/python src/models/baseline_anomaly.py
	$(VENV)/python src/models/evaluate.py
	$(VENV)/python src/models/explain.py

app:             ## run the Service Command Center locally
	$(VENV)/streamlit run src/app/Home.py

test:
	$(VENV)/pytest tests/ -q

sample:          ## build the small committed sample for the cloud deployment
	$(VENV)/python src/pipeline/make_sample.py

all: data features train
