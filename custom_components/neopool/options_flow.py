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

from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

# CUSTOM-ONLY START
from homeassistant.util import dt as dt_util, slugify

# CUSTOM-ONLY END
from .const import (
    CONF_DEV_OVERRIDES,
    CONF_DEV_OVERRIDES_ENABLED,
    CONF_ENABLE_BACKWASH_OPTION,
    CONF_FILTRATION_PUMP_POWER,
    CONF_MEASURE_WHEN_FILTRATION_OFF,
    CONF_SCAN_INTERVAL,
    CONF_USE_AUX1,
    CONF_USE_AUX2,
    CONF_USE_AUX3,
    CONF_USE_AUX4,
    CONF_USE_COVER_SENSOR,
    CONF_USE_FILTRATION1,
    CONF_USE_FILTRATION2,
    CONF_USE_FILTRATION3,
    CONF_USE_LIGHT,
    # CUSTOM-ONLY START
    DEFAULT_SCAN_INTERVAL,
    # CUSTOM-ONLY END
)

_LOGGER = logging.getLogger(__name__)


class NeoPoolOptionsFlowHandler(OptionsFlowWithReload):
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
        already_enabled = options.get(CONF_ENABLE_BACKWASH_OPTION, False)

        device_slug = slugify(self.config_entry.title)
        expected = f"{device_slug}{dt_util.now().year}"
        # CUSTOM-ONLY END

        schema_dict = {
            # CUSTOM-ONLY START
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=str(options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[str(v) for v in (5, 10, 15, 20, 30, 45, 60, 120, 180, 300)]
                )
            ),
            # CUSTOM-ONLY END
            vol.Optional(
                CONF_MEASURE_WHEN_FILTRATION_OFF,
                default=options.get(CONF_MEASURE_WHEN_FILTRATION_OFF, False),
            ): bool,
            vol.Optional(
                CONF_FILTRATION_PUMP_POWER,
                default=options.get(CONF_FILTRATION_PUMP_POWER, 0),
            ): vol.All(int, vol.Range(min=0)),
            vol.Optional(
                CONF_USE_FILTRATION1,
                default=options.get(CONF_USE_FILTRATION1, False),
            ): bool,
            vol.Optional(
                CONF_USE_FILTRATION2,
                default=options.get(CONF_USE_FILTRATION2, False),
            ): bool,
            vol.Optional(
                CONF_USE_FILTRATION3,
                default=options.get(CONF_USE_FILTRATION3, False),
            ): bool,
            vol.Optional(
                CONF_USE_LIGHT,
                default=options.get(CONF_USE_LIGHT, False),
            ): bool,
            vol.Optional(
                CONF_USE_COVER_SENSOR,
                default=options.get(CONF_USE_COVER_SENSOR, False),
            ): bool,
            vol.Optional(
                CONF_USE_AUX1,
                default=options.get(CONF_USE_AUX1, False),
            ): bool,
            vol.Optional(
                CONF_USE_AUX2,
                default=options.get(CONF_USE_AUX2, False),
            ): bool,
            vol.Optional(
                CONF_USE_AUX3,
                default=options.get(CONF_USE_AUX3, False),
            ): bool,
            vol.Optional(
                CONF_USE_AUX4,
                default=options.get(CONF_USE_AUX4, False),
            ): bool,
        }

        # CUSTOM-ONLY START
        if already_enabled:
            schema_dict[
                vol.Optional(
                    CONF_ENABLE_BACKWASH_OPTION,
                    default=True,
                    description={"suggested_value": True},
                )
            ] = bool
        schema_dict[vol.Optional("unlock_advanced", default="")] = str
        # CUSTOM-ONLY END

        schema = vol.Schema(schema_dict)

        if user_input is not None:
            # CUSTOM-ONLY START
            if CONF_SCAN_INTERVAL in user_input:
                user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
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
            return self.async_create_entry(title="", data=data)

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
                    CONF_ENABLE_BACKWASH_OPTION,
                    default=options.get(CONF_ENABLE_BACKWASH_OPTION, False),
                ): bool,
                vol.Optional(
                    CONF_DEV_OVERRIDES_ENABLED,
                    default=options.get(CONF_DEV_OVERRIDES_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_DEV_OVERRIDES,
                    default=options.get(CONF_DEV_OVERRIDES, "{}"),
                ): str,
            }
        )

        if user_input is not None:
            all_options = {**self._base_options, **user_input}
            return self.async_create_entry(title="", data=all_options)

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
