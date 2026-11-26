#include "headsetcontrols.h"
#include <QLocalSocket>
#include <QJsonDocument>
#include <QJsonParseError>
#include <utility>

HeadsetControls::HeadsetControls(Writer writer, QObject *parent)
    : QObject(parent), writer(std::move(writer)) {
    confirmation.setSingleShot(true);
    confirmation.setInterval(3000);
    connect(&confirmation, &QTimer::timeout, this, [this] {
        pending.clear();
        error = "The headset did not confirm the noise-control change.";
        emit changed();
    });
    server.setSocketOptions(QLocalServer::UserAccessOption);
    connect(&server, &QLocalServer::newConnection, this, [this] {
        while (auto client = server.nextPendingConnection()) {
            client->setReadBufferSize(1025);
            auto timeout = new QTimer(client);
            timeout->setSingleShot(true);
            connect(timeout, &QTimer::timeout, client, &QLocalSocket::abort);
            timeout->start(3000);
            connect(client, &QLocalSocket::disconnected, client, &QObject::deleteLater);
            connect(client, &QLocalSocket::readyRead, this, [this, client, timeout] {
                if (client->property("handled").toBool()) return;
                if (client->bytesAvailable() > 1024) { client->abort(); return; }
                if (!client->canReadLine()) return;
                client->setProperty("handled", true);
                timeout->stop();
                QJsonParseError parse;
                auto doc = QJsonDocument::fromJson(client->readLine(), &parse);
                auto reply = parse.error == QJsonParseError::NoError && doc.isObject()
                    ? request(doc.object())
                    : QJsonObject{{"ok", false}, {"error", "Invalid command."}};
                client->write(QJsonDocument(reply).toJson(QJsonDocument::Compact) + '\n');
                client->disconnectFromServer();
            });
        }
    });
}

bool HeadsetControls::listen(const QString &path) {
    // The process holds the per-device lock before constructing this object.
    QLocalServer::removeServer(path);
    return server.listen(path);
}

void HeadsetControls::setReady(bool value) {
    ready = value;
    if (!ready) {
        confirmation.stop();
        mode.clear(); pending.clear(); error.clear();
        left = right = caseLevel = -1;
        leftCharging = rightCharging = caseCharging = false;
    }
    emit changed();
}

QJsonObject HeadsetControls::status() const {
    return {{"controls_ready", ready && !mode.isEmpty()},
            {"noise_control", mode}, {"noise_pending", pending},
            {"control_error", error}, {"battery_left", left},
            {"battery_right", right}, {"battery_case", caseLevel},
            {"charging_left", leftCharging}, {"charging_right", rightCharging},
            {"charging_case", caseCharging}};
}

QJsonObject HeadsetControls::request(const QJsonObject &command) {
    auto reject = [](const QString &message) {
        return QJsonObject{{"ok", false}, {"error", message}};
    };
    if (command.value("command") == "status")
        return {{"ok", true}, {"status", status()}};
    if (command.value("command") != "set-noise-control")
        return reject("Unknown control command.");
    const auto wanted = command.value("mode").toString();
    const auto modes = QStringList{"off", "anc", "transparency"};
    const int index = modes.indexOf(wanted);
    if (index < 0) return reject("Choose Off, Noise Cancellation, or Transparency.");
    if (!ready) return reject("The headset control connection is unavailable.");
    if (mode.isEmpty()) return reject("Waiting for the headset to announce noise-control support.");
    if (!pending.isEmpty()) return reject("Waiting for the previous change to be confirmed.");
    QByteArray packet = QByteArray::fromHex("0400040009000d00000000");
    packet[7] = static_cast<char>(index + 1);
    if (writer(packet) != packet.size()) return reject("Could not send the headset command.");
    // Acceptance is not confirmation. The UI retains the reported mode until
    // the headset echoes the requested setting, including when audio is elsewhere.
    pending = wanted;
    error.clear();
    confirmation.start();
    emit changed();
    return {{"ok", true}, {"status", status()}};
}

void HeadsetControls::receive(const QByteArray &packet) {
    if (!ready || packet.size() < 7 || !packet.startsWith(QByteArray::fromHex("04000400"))) return;
    const auto byte = [&packet](int offset) { return static_cast<quint8>(packet[offset]); };
    if (byte(4) == 0x09 && byte(5) == 0 && byte(6) == 0x0D && packet.size() >= 8) {
        const auto modes = QStringList{"", "off", "anc", "transparency", "adaptive"};
        if (byte(7) < 1 || byte(7) > 4) return;
        mode = modes[byte(7)];
        if (mode == pending) { pending.clear(); error.clear(); confirmation.stop(); }
        emit changed();
    } else if (byte(4) == 0x04 && byte(5) == 0) {
        const int count = byte(6);
        if (count < 1 || count > 3 || packet.size() < 7 + 5 * count) return;
        left = right = caseLevel = -1;
        leftCharging = rightCharging = caseCharging = false;
        for (int i = 0; i < count; ++i) {
            const int offset = 7 + i * 5;
            const int level = byte(offset + 2) <= 100 && byte(offset + 3) != 4
                ? byte(offset + 2) : -1;
            const bool charging = level >= 0 && byte(offset + 3) == 1;
            switch (byte(offset)) {
            case 1: case 4: left = level; leftCharging = charging; break;
            case 2: right = level; rightCharging = charging; break;
            case 8: caseLevel = level; caseCharging = charging; break;
            default: break;
            }
        }
        emit changed();
    }
}
