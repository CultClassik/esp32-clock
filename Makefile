UV := uv run
FIRMWARE := ESP32_GENERIC-20250911-v1.26.1.bin
SERIAL_PORT ?= $(firstword $(wildcard /dev/tty.usb*))
SECRETS_ENC := secrets.sops.py

# Runtime files main.py needs on the device (not dev-only scripts like demo.py)
DEPLOY_FILES := main.py secrets.py ili9341.py xglcd_font.py ds1307.py fonts

.PHONY: help
help:
	@echo "Targets:"
	@echo "  make fmt       - format Python source files (via ruff)"
	@echo "  make sync      - install Python dev dependencies (uv sync)"
	@echo "  make erase     - erase the ESP32's flash"
	@echo "  make flash     - erase + write MicroPython firmware ($(FIRMWARE))"
	@echo "  make deploy    - copy main.py and its dependencies onto the device"
	@echo "  make setrtc    - run rtc.py on the device to set the DS1307's clock"
	@echo "  make monitor   - open a serial monitor on the device"
	@echo "  make decrypt-secrets - decrypt $(SECRETS_ENC) to secrets.py (via sops)"
	@echo "  make encrypt-secrets - re-encrypt secrets.py to $(SECRETS_ENC) after editing it"
	@echo "  make clean     - remove local build/cache artifacts"
	@echo ""
	@echo "SERIAL_PORT is auto-detected from /dev/tty.usb*; override with"
	@echo "  make deploy SERIAL_PORT=/dev/tty.usbserial-XXXX"

.PHONY: fmt
fmt:
	$(UV) ruff check --fix .

.PHONY: check-port
check-port:
	@if [ -z "$(SERIAL_PORT)" ]; then \
		echo "No SERIAL_PORT found/set. Plug in the board or pass SERIAL_PORT=/dev/tty.usbXXXX"; \
		exit 1; \
	fi

.PHONY: sync
sync:
	uv sync

.PHONY: erase
erase: check-port sync
	$(UV) esptool --chip esp32 --port "$(SERIAL_PORT)" erase-flash

.PHONY: flash
flash: check-port sync erase
	$(UV) esptool --chip esp32 --port "$(SERIAL_PORT)" write_flash -z 0x1000 $(FIRMWARE)

.PHONY: deploy
deploy: check-port sync secrets.py
	@for f in $(DEPLOY_FILES); do \
		echo "Putting $$f..."; \
		$(UV) ampy --port "$(SERIAL_PORT)" put $$f || exit 1; \
	done

# secrets.py is gitignored plaintext, decrypted on demand from the
# sops-encrypted secrets.sops.py that's actually committed.
secrets.py: $(SECRETS_ENC)
	sops --decrypt $(SECRETS_ENC) > secrets.py

.PHONY: decrypt-secrets
decrypt-secrets:
	sops --decrypt $(SECRETS_ENC) > secrets.py

.PHONY: encrypt-secrets
encrypt-secrets:
	sops --encrypt --output $(SECRETS_ENC) secrets.py

.PHONY: setrtc
setrtc: check-port sync
	$(UV) ampy --port "$(SERIAL_PORT)" run rtc.py

.PHONY: monitor
monitor: check-port sync
	$(UV) python -m serial.tools.miniterm "$(SERIAL_PORT)" 115200

.PHONY: clean
clean:
	rm -rf __pycache__ .venv
