import network

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect("telenet-34BF9", "s1pzctYeMMY9")

while not wlan.isconnected():
    pass

print(wlan.ifconfig())  # prints (ip, subnet, gateway, dns)