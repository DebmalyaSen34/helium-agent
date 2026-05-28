import os
import yaml
from evals.schema import TaskConfig

def test_task_config_parsing():
    yaml_content = """
    id: "test_task"
    description: "A test task"
    category: "coding"
    input_prompt: "Do something"
    setup: "echo 'setup'"
    teardown: "echo 'teardown'"
    graders:
      - type: "file_modified"
        params:
          path: "core/todo.py"
    """
    data = yaml.safe_load(yaml_content)
    config = TaskConfig.from_dict(data)
    assert config.id == "test_task"
    assert config.description == "A test task"
    assert config.category == "coding"
    assert config.input_prompt == "Do something"
    assert config.setup == "echo 'setup'"
    assert config.teardown == "echo 'teardown'"
    assert len(config.graders) == 1
    assert config.graders[0].type == "file_modified"
    assert config.graders[0].params["path"] == "core/todo.py"
