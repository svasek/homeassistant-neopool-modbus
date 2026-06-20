# Copyright 2025 Miloš Svašek

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Options flow for the NeoPool integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

# CUSTOM-ONLY START
from homeassistant.util import dt as dt_util, slugify

# CUSTOM-ONLY END
from .const import (
    CONF_FILTRATION_PUMP_POWER,
    # CUSTOM-ONLY START
    DEFAULT_SCAN_INTERVAL,
    # CUSTOM-ONLY END
)

_LOGGER = logging.getLogger(__name__)


class NeoPoolOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for NeoPool integration."""

    def __init__(self) -> None:
        """Initialize the options flow handler.

        config_entry is not injected here; it is available as the read-only
        self.config_entry property provided by the OptionsFlow base class.
        """
        super().__init__()
        self._base_options: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step of the options flow."""
        options = dict(self.config_entry.options)
        # CUSTOM-ONLY START
        already_enabled = options.get("enable_backwash_option", False)

        device_slug = slugify(self.config_entry.title)
        expected = f"{device_slug}{dt_util.now().year}"
        # CUSTOM-ONLY END

        schema_dict = {
            # CUSTOM-ONLY START
            vol.Optional(
                "scan_interval",
                default=str(options.get("scan_interval", DEFAULT_SCAN_INTERVAL)),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[str(v) for v in (5, 10, 15, 20, 30, 45, 60, 120, 180, 300)]
                )
            ),
            # CUSTOM-ONLY END
            vol.Optional(
                "measure_when_filtration_off",
                default=options.get("measure_when_filtration_off", False),
            ): bool,
            vol.Optional(
                CONF_FILTRATION_PUMP_POWER,
                default=options.get(CONF_FILTRATION_PUMP_POWER, 0),
            ): vol.All(int, vol.Range(min=0)),
            vol.Optional(
                "use_filtration1",
                default=options.get("use_filtration1", True),
            ): bool,
            vol.Optional(
                "use_filtration2",
                default=options.get("use_filtration2", False),
            ): bool,
            vol.Optional(
                "use_filtration3",
                default=options.get("use_filtration3", False),
            ): bool,
            vol.Optional(
                "use_light",
                default=options.get("use_light", False),
            ): bool,
            vol.Optional(
                "use_cover_sensor",
                default=options.get("use_cover_sensor", False),
            ): bool,
            vol.Optional(
                "use_aux1",
                default=options.get("use_aux1", False),
            ): bool,
            vol.Optional(
                "use_aux2",
                default=options.get("use_aux2", False),
            ): bool,
            vol.Optional(
                "use_aux3",
                default=options.get("use_aux3", False),
            ): bool,
            vol.Optional(
                "use_aux4",
                default=options.get("use_aux4", False),
            ): bool,
        }

        # CUSTOM-ONLY START
        if already_enabled:
            schema_dict[
                vol.Optional(
                    "enable_backwash_option",
                    default=True,
                    description={"suggested_value": True},
                )
            ] = bool
        schema_dict[vol.Optional("unlock_advanced", default="")] = str
        # CUSTOM-ONLY END

        schema = vol.Schema(schema_dict)

        if user_input is not None:
            # CUSTOM-ONLY START
            if "scan_interval" in user_input:
                user_input["scan_interval"] = int(user_input["scan_interval"])
            if (user_input.get("unlock_advanced") or "").strip() == expected:
                self._base_options = user_input.copy()
                self._base_options.pop("unlock_advanced", None)
                return await self.async_step_advanced()
            if (user_input.get("unlock_advanced") or "").strip() != "":
                _LOGGER.warning("Wrong password for the advanced settings!")
                return self.async_show_form(
                    step_id="init",
                    data_schema=schema,
                    errors={"unlock_advanced": "unlock_advanced_error"},
                )
            # CUSTOM-ONLY END
            data = user_input.copy()
            # CUSTOM-ONLY START
            data.pop("unlock_advanced", None)
            # CUSTOM-ONLY END
            prev_options = dict(self.config_entry.options)
            result = self.async_create_entry(title="", data=data)

            if any(
                prev_options.get(k) != data.get(k)
                for k in set(prev_options) | set(data)
            ):
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.config_entry.entry_id)
                )

            return result

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={},
        )

    # CUSTOM-ONLY START
    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the advanced options step."""
        options = dict(self.config_entry.options)
        advanced_schema = vol.Schema(
            {
                vol.Optional(
                    "enable_backwash_option",
                    default=options.get("enable_backwash_option", False),
                ): bool,
                vol.Optional(
                    "dev_overrides_enabled",
                    default=options.get("dev_overrides_enabled", False),
                ): bool,
                vol.Optional(
                    "dev_overrides",
                    default=options.get("dev_overrides", "{}"),
                ): str,
            }
        )

        if user_input is not None:
            prev_options = dict(self.config_entry.options)
            all_options = {**self._base_options, **user_input}
            result = self.async_create_entry(title="", data=all_options)

            if any(
                prev_options.get(k) != all_options.get(k)
                for k in set(prev_options) | set(all_options)
            ):
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.config_entry.entry_id)
                )

            return result

        return self.async_show_form(
            step_id="advanced",
            data_schema=advanced_schema,
            description_placeholders={
                "warning": (
                    "WARNING: Enabling backwash will add this mode to Filtration Mode select. "
                    "Improper use may damage the filter! Enable only if you know what you are doing."
                )
            },
            last_step=True,
        )

    # CUSTOM-ONLY END
