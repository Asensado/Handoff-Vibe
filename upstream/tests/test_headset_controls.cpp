#include "headsetcontrols.h"
#include <QCoreApplication>
#include <QEventLoop>
#include <QJsonArray>
#include <QTemporaryDir>
#include <QLocalSocket>
#include <QJsonDocument>
#include <cstdlib>
#include <iostream>

#define CHECK(value) do { if (!(value)) { std::cerr << "Failed at line " << __LINE__ << ": " << #value << '\n'; std::exit(1); } } while (false)

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    QList<QByteArray> writes;
    HeadsetControls controls([&writes](const QByteArray &packet) {
        writes.append(packet); return packet.size();
    });
    auto request = [](const QString &mode) { return QJsonObject{{"command", "set-noise-control"}, {"mode", mode}}; };
    CHECK(!controls.request(request("anc"))["ok"].toBool());
    controls.setReady(true);
    CHECK(!controls.request(request("anc"))["ok"].toBool());
    controls.receive(QByteArray::fromHex("0400040009000d02000000"));
    CHECK(controls.status()["controls_ready"].toBool());
    CHECK(controls.status()["noise_control"] == "anc");
    CHECK(!controls.request(request("adaptive"))["ok"].toBool());
    CHECK(!controls.request({{"command", "raw"}})["ok"].toBool());
    CHECK(writes.isEmpty());

    // All three controls send only setting 0x0D over the existing connection.
    // There is no ownership command 0x06 and no Bluetooth reconnect path.
    const QStringList modes{"off", "anc", "transparency"};
    for (int i = 0; i < modes.size(); ++i) {
        const QJsonValue previous = controls.status()["noise_control"];
        CHECK(controls.request(request(modes[i]))["ok"].toBool());
        CHECK(controls.status()["noise_pending"] == modes[i]);
        CHECK(controls.status()["noise_control"] == previous);
        CHECK(!controls.request(request("anc"))["ok"].toBool());
        auto expected = QByteArray::fromHex("0400040009000d00000000");
        expected[7] = static_cast<char>(i + 1);
        CHECK(writes.last() == expected);
        controls.receive(expected);
        CHECK(controls.status()["noise_control"] == modes[i]);
        CHECK(controls.status()["noise_pending"] == "");
    }
    controls.receive(QByteArray::fromHex("04000400040003040053020002004b01000800000400"));
    CHECK(controls.status()["battery_left"] == 83);
    CHECK(controls.status()["battery_right"] == 75);
    CHECK(controls.status()["charging_right"].toBool());
    CHECK(controls.status()["battery_case"] == -1);
    const auto before = controls.status();
    controls.receive(QByteArray::fromHex("04000400040003040001"));
    controls.receive(QByteArray::fromHex("0400040009000dff"));
    CHECK(controls.status() == before);
    CHECK(controls.request(request("off"))["ok"].toBool());
    QEventLoop loop;
    QTimer::singleShot(3300, &loop, &QEventLoop::quit);
    loop.exec();
    CHECK(controls.status()["noise_pending"] == "");
    CHECK(!controls.status()["control_error"].toString().isEmpty());
    CHECK(controls.status()["noise_control"] == "transparency");

    HeadsetControls broken([](const QByteArray &) -> qint64 { return -1; });
    broken.setReady(true);
    broken.receive(QByteArray::fromHex("0400040009000d02"));
    CHECK(!broken.request(request("off"))["ok"].toBool());
    CHECK(broken.status()["noise_pending"] == "");
    controls.setReady(false);
    CHECK(!controls.status()["controls_ready"].toBool());
    CHECK(controls.status()["battery_left"] == -1);
    CHECK(controls.status()["noise_control"] == "");
    CHECK(!controls.request(request("off"))["ok"].toBool());
    std::cout << "Headset controls: packet validation, confirmation, timeout, write failure, reset passed.\n";
}
