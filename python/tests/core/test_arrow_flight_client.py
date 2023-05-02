#
#   Copyright 2023 Hopsworks AB
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
import pandas as pd

from hsfs import feature_group, feature_view, training_dataset
from hsfs.constructor import fs_query
from hsfs.core import arrow_flight_client
from hsfs.engine import python
from hsfs.storage_connector import HopsFSConnector


class TestArrowFlightClient:
    def _arrange_engine_mocks(self, mocker, backend_fixtures):
        mocker.patch("hsfs.engine.get_type", return_value="python")
        python_engine = python.Engine()
        arrow_flight_client.get_instance()._is_enabled = True
        mocker.patch("hsfs.engine.get_instance", return_value=python_engine)
        mocker.patch("hsfs.client.get_instance")
        json_query = backend_fixtures["fs_query"]["get_basic_info"]["response"]
        q = fs_query.FsQuery.from_response_json(json_query)
        mocker.patch(
            "hsfs.core.query_constructor_api.QueryConstructorApi.construct_query",
            return_value=q,
        )

    def _arrange_featuregroup_mocks(self, mocker, backend_fixtures):
        json_fg = backend_fixtures["feature_group"]["get_stream_list"]["response"]
        fg_list = feature_group.FeatureGroup.from_response_json(json_fg)
        fg = fg_list[0]
        return fg

    def _arrange_featureview_mocks(self, mocker, backend_fixtures):
        json_fv = backend_fixtures["feature_view"]["get"]["response"]
        fv = feature_view.FeatureView.from_response_json(json_fv)
        json_td = backend_fixtures["training_dataset"]["get_basic_info"]["response"]
        td = training_dataset.TrainingDataset.from_response_json(json_td)[0]
        td.training_dataset_type = "IN_MEMORY_TRAINING_DATASET"
        mocker.patch(
            "hsfs.core.feature_view_engine.FeatureViewEngine._create_training_data_metadata",
            return_value=td,
        )

        fg = self._arrange_featuregroup_mocks(mocker, backend_fixtures)
        mocker.patch(
            "hsfs.core.feature_view_engine.FeatureViewEngine.get_batch_query",
            return_value=fg.select_all(),
        )
        mocker.patch(
            "hsfs.core.transformation_function_engine.TransformationFunctionEngine.populate_builtin_transformation_functions"
        )
        mocker.patch("hsfs.engine.python.Engine._apply_transformation_function")

        # required for batch query
        batch_scoring_server = mocker.MagicMock()
        batch_scoring_server.training_dataset_version = 1
        batch_scoring_server._transformation_functions = None
        fv._batch_scoring_server = batch_scoring_server
        mocker.patch("hsfs.feature_view.FeatureView.init_batch_scoring")

        return fv

    def _arrange_dataset_reads(self, mocker, backend_fixtures, data_format):
        # required for reading tds from path
        json_td = backend_fixtures["training_dataset"]["get_basic_info"]["response"]
        td_hopsfs = training_dataset.TrainingDataset.from_response_json(json_td)[0]
        td_hopsfs.training_dataset_type = "HOPSFS_TRAINING_DATASET"
        td_hopsfs.storage_connector = HopsFSConnector(0, "", "")
        td_hopsfs.data_format = data_format
        mocker.patch(
            "hsfs.core.feature_view_engine.FeatureViewEngine._get_training_data_metadata",
            return_value=td_hopsfs,
        )
        mocker.patch("hsfs.storage_connector.StorageConnector.refetch")
        inode_path = mocker.MagicMock()
        inode_path.path = "/path/test.parquet"
        mocker.patch(
            "hsfs.core.dataset_api.DatasetApi.list_files",
            return_value=(1, [inode_path]),
        )
        mocker.patch("hsfs.engine.python.Engine.split_labels", return_value=None)

    def test_read_feature_group(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        fg = self._arrange_featuregroup_mocks(mocker, backend_fixtures)
        mock_read_query = mocker.patch(
            "hsfs.core.arrow_flight_client.ArrowFlightClient.read_query"
        )

        # Act
        fg.read()

        # Assert
        assert mock_read_query.call_count == 1

    def test_read_feature_group_spark(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        fg = self._arrange_featuregroup_mocks(mocker, backend_fixtures)
        mock_creat_hive_connection = mocker.patch(
            "hsfs.engine.python.Engine._create_hive_connection"
        )

        # Act
        fg.read(read_options={"use_hive": True})

        # Assert
        assert mock_creat_hive_connection.call_count == 1

    def test_read_query(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        fg = self._arrange_featuregroup_mocks(mocker, backend_fixtures)
        mock_read_query = mocker.patch(
            "hsfs.core.arrow_flight_client.ArrowFlightClient.read_query"
        )
        query = fg.select_all()

        # Act
        query.read()

        # Assert
        assert mock_read_query.call_count == 1

    def test_read_query_spark(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        fg = self._arrange_featuregroup_mocks(mocker, backend_fixtures)
        mock_creat_hive_connection = mocker.patch(
            "hsfs.engine.python.Engine._create_hive_connection"
        )
        query = fg.select_all()

        # Act
        query.read(read_options={"use_hive": True})

        # Assert
        assert mock_creat_hive_connection.call_count == 1

    def test_training_data_featureview(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        fv = self._arrange_featureview_mocks(mocker, backend_fixtures)
        mock_read_query = mocker.patch(
            "hsfs.core.arrow_flight_client.ArrowFlightClient.read_query"
        )

        # Act
        fv.training_data()

        # Assert
        assert mock_read_query.call_count == 1

    def test_training_data_featureview_spark(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        fv = self._arrange_featureview_mocks(mocker, backend_fixtures)
        mock_creat_hive_connection = mocker.patch(
            "hsfs.engine.python.Engine._create_hive_connection"
        )

        # Act
        fv.training_data(read_options={"use_hive": True})

        # Assert
        assert mock_creat_hive_connection.call_count == 1

    def test_batch_data_featureview(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        fv = self._arrange_featureview_mocks(mocker, backend_fixtures)
        mock_read_query = mocker.patch(
            "hsfs.core.arrow_flight_client.ArrowFlightClient.read_query"
        )

        # Act
        fv.get_batch_data()

        # Assert
        assert mock_read_query.call_count == 1

    def test_batch_data_featureview_spark(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        fv = self._arrange_featureview_mocks(mocker, backend_fixtures)
        mock_creat_hive_connection = mocker.patch(
            "hsfs.engine.python.Engine._create_hive_connection"
        )

        # Act
        fv.get_batch_data(read_options={"use_hive": True})

        # Assert
        assert mock_creat_hive_connection.call_count == 1

    def test_get_training_data_featureview(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        fv = self._arrange_featureview_mocks(mocker, backend_fixtures)
        self._arrange_dataset_reads(mocker, backend_fixtures, "parquet")
        mock_read_path = mocker.patch(
            "hsfs.core.arrow_flight_client.ArrowFlightClient.read_path",
            return_value=pd.DataFrame(),
        )

        # Act
        fv.get_training_data(1)

        # Assert
        assert mock_read_path.call_count == 1

    def test_get_training_data_featureview_spark(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        fv = self._arrange_featureview_mocks(mocker, backend_fixtures)
        self._arrange_dataset_reads(mocker, backend_fixtures, "parquet")
        stream = mocker.MagicMock()
        stream.content = b""
        mock_read_file = mocker.patch(
            "hsfs.core.dataset_api.DatasetApi.read_content", return_value=stream
        )
        mock_read_pandas = mocker.patch(
            "hsfs.engine.python.Engine._read_pandas", return_value=pd.DataFrame()
        )

        # Act
        fv.get_training_data(1, read_options={"use_hive": True})

        # Assert
        assert mock_read_file.call_count == 1
        assert mock_read_pandas.call_count == 1

    def _find_diff(self, dict1, dict2, path=""):
        diff = {}
        for key in set(dict1.keys()).union(dict2.keys()):
            subpath = f"{path}.{key}" if path else key
            if key not in dict1 or key not in dict2:
                diff[subpath] = {"dict1": dict1.get(key), "dict2": dict2.get(key)}
            elif isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
                sub_diff = self._find_diff(dict1[key], dict2[key], subpath)
                if sub_diff:
                    diff.update(sub_diff)
            elif isinstance(dict1[key], list) and isinstance(dict2[key], list):
                if sorted(dict1[key]) != sorted(dict2[key]):
                    diff[subpath] = {"dict1": dict1[key], "dict2": dict2[key]}
            elif dict1[key] != dict2[key]:
                diff[subpath] = {"dict1": dict1[key], "dict2": dict2[key]}

        return diff

    def test_construct_query_object(self, mocker, backend_fixtures):
        # Arrange
        self._arrange_engine_mocks(mocker, backend_fixtures)
        json1 = backend_fixtures["feature_group"]["get"]["response"]
        test_fg1 = feature_group.FeatureGroup.from_response_json(json1)
        json2 = backend_fixtures["feature_group"]["get_stream"]["response"]
        test_fg2 = feature_group.FeatureGroup.from_response_json(json2)
        mocker.patch("hsfs.constructor.query.Query.to_string", return_value="")
        mocker.patch("hsfs.constructor.query.Query._to_string", return_value="")
        query = (
            test_fg1.select_all()
            .filter((test_fg1.features[0] > 500) & (test_fg1.features[1] < 0.1))
            .join(
                test_fg2.filter(test_fg2.features[0] > 500),
                left_on=["intt"],
                right_on=["intt"],
            )
            .filter(test_fg1.features[0] < 700)
        )

        # Act
        query_object = arrow_flight_client.get_instance()._construct_query_object(
            query, "SELECT * FROM..."
        )

        # Assert
        query_object_reference = {
            "query_string": "SELECT * FROM...",
            "featuregroups": {15: "test.fg_test_1"},
            "features": {"test.fg_test_1": ["intt", "stringt"]},
            "filters": {
                "type": "logic",
                "logic_type": "AND",
                "left_filter": {
                    "type": "logic",
                    "logic_type": "AND",
                    "left_filter": {
                        "type": "logic",
                        "logic_type": "AND",
                        "left_filter": {
                            "type": "filter",
                            "condition": "GREATER_THAN",
                            "value": 500,
                            "feature": "test.fg_test_1.intt",
                            "numeric": True,
                        },
                        "right_filter": {
                            "type": "filter",
                            "condition": "LESS_THAN",
                            "value": 0.1,
                            "feature": "test.fg_test_1.stringt",
                            "numeric": False,
                        },
                    },
                    "right_filter": {
                        "type": "filter",
                        "condition": "LESS_THAN",
                        "value": 700,
                        "feature": "test.fg_test_1.intt",
                        "numeric": True,
                    },
                },
                "right_filter": {
                    "type": "logic",
                    "logic_type": "SINGLE",
                    "left_filter": {
                        "type": "filter",
                        "condition": "GREATER_THAN",
                        "value": 500,
                        "feature": "test.fg_test_1.intt",
                        "numeric": True,
                    },
                    "right_filter": None,
                },
            },
        }

        diff = self._find_diff(query_object, query_object_reference)
        assert diff == {}