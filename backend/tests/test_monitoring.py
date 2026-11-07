from app.monitoring import ThresholdMonitor

def test_hysteresis_sustain_and_cooldown():
    m=ThresholdMonitor()
    assert not m.check('gpu',90,high=85,low=78,sustain=10,cooldown=60,now=0)
    assert not m.check('gpu',90,high=85,low=78,sustain=10,cooldown=60,now=9)
    assert m.check('gpu',90,high=85,low=78,sustain=10,cooldown=60,now=10)
    assert not m.check('gpu',90,high=85,low=78,sustain=10,cooldown=60,now=100)
    assert not m.check('gpu',77,high=85,low=78,sustain=10,cooldown=60,now=101)
    assert not m.check('gpu',90,high=85,low=78,sustain=10,cooldown=60,now=102)
    assert m.check('gpu',90,high=85,low=78,sustain=10,cooldown=60,now=112)
