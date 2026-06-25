# kick_chat 2.1.8

Kick-Integration für godisalotachat.

## Enthalten

- bestehender Kick-Realtime/Pusher-Websocket für normale Chatnachrichten
- normale Chats bleiben `chat_no_alert`
- kein Fake-Join aus Chatnachrichten
- optionaler offizieller Kick-Webhook-Eingang für echte Alerts
- Event-Subscription-Versuch beim Start, wenn eine öffentliche Webhook-URL gesetzt ist

## Unterstützte Kick-Webhooks

- `channel.followed` -> `kick_follow`
- `channel.subscription.new` -> `kick_sub`
- `channel.subscription.renewal` -> `kick_sub`
- `channel.subscription.gifts` -> `kick_gift`
- `kicks.gifted` -> `kick_gift`
- `livestream.status.updated` -> Live-Status-Metric

`chat.message.sent` wird nicht als Webhook-Chat emittiert, weil Chat bereits über den bestehenden Realtime-Websocket kommt.

## Wichtige Voraussetzung

Kick muss nach dem Core-Scope-Update neu verbunden werden, damit der Token den Scope `events:subscribe` enthält.

Für Webhooks braucht Kick eine öffentliche URL, zum Beispiel:

`https://dein-tunnel.example/api/webhooks/kick`

Lokal `127.0.0.1` reicht nicht, weil Kick diese Adresse nicht erreichen kann.

## Diagnose

Die Diagnose steht unter:

`data/kick_chat/kick_chat_last_diag.txt`
