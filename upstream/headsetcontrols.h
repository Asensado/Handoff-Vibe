#pragma once
#include <QObject>
#include <QByteArray>
#include <QJsonObject>
#include <QLocalServer>
#include <QTimer>
#include <functional>

// One local command endpoint; all headset writes use Handoff's existing AACP
// socket. This class never claims audio, reconnects Bluetooth, or opens AACP.
class HeadsetControls : public QObject {
    Q_OBJECT
public:
    using Writer = std::function<qint64(const QByteArray &)>;
    explicit HeadsetControls(Writer writer, QObject *parent = nullptr);
    bool listen(const QString &path);
    void setReady(bool ready);
    void receive(const QByteArray &packet);
    QJsonObject status() const;
    QJsonObject request(const QJsonObject &command);
signals:
    void changed();
private:
    Writer writer;
    QLocalServer server;
    QTimer confirmation;
    bool ready = false;
    QString mode, pending, error;
    int left = -1, right = -1, caseLevel = -1;
    bool leftCharging = false, rightCharging = false, caseCharging = false;
};
