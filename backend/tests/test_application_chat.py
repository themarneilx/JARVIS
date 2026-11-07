import json
from app.application_chat import launch_feedback,launch_request

def test_only_real_pending_actions_can_describe_a_prepared_launch():
    action={'id':'review','kind':'launch','target':'app-fixture','effect':'Launch Editor','expires':123,'status':'pending'}
    rows=[{'role':'user','content':'Open Editor'},{'role':'tool','tool_name':'jarvis_launch_application','content':json.dumps(action)}]
    assert 'approval' in launch_feedback(rows,[action])
    assert 'not been launched' in launch_feedback(rows,[action])
    assert "haven't opened" in launch_feedback(rows,[{**action,'target':'another'}])
    assert "haven't opened" in launch_feedback(rows,[])
    assert launch_request('Jarvis, please open Firefox.')
    assert not launch_request('What is open source software?')
