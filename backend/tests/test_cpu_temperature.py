from types import SimpleNamespace
from app.telemetry import cpu_temperature


def test_prefers_cpu_package_reading_over_cores_and_other_devices():
    sensor=lambda label,current:SimpleNamespace(label=label,current=current)
    readings={'coretemp':[sensor('Core 0',62),sensor('Package id 0',58)],'nvme':[sensor('Composite',90)],'acpitz':[sensor('',80)]}
    assert cpu_temperature(readings)==(58.0,'coretemp / Package id 0')


def test_missing_cpu_sensor_is_unavailable_not_an_acpi_guess():
    assert cpu_temperature({'acpitz':[SimpleNamespace(label='',current=50)]})==(None,None)
    assert cpu_temperature({})==(None,None)
