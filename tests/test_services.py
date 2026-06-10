import pytest

from domain import Notification


class TestNotification:
    def test_notification_creation_with_valid_data(self):
        notif = Notification(target_name="Grupo", message="Ola")
        assert notif.target_name == "Grupo"
        assert notif.message == "Ola"

    def test_notification_raises_on_empty_target(self):
        with pytest.raises(ValueError, match="n.o pode estar vazio"):
            Notification(target_name="", message="Valid")

    def test_notification_raises_on_whitespace_target(self):
        with pytest.raises(ValueError, match="n.o pode estar vazio"):
            Notification(target_name="   ", message="Valid")

    def test_notification_raises_on_empty_message(self):
        with pytest.raises(ValueError, match="n.o pode estar vazio"):
            Notification(target_name="Valid", message="")

    def test_notification_is_immutable(self):
        notif = Notification(target_name="Grupo", message="Ola")

        with pytest.raises(AttributeError):
            notif.target_name = "Outro"
