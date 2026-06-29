# Changelog

## [6.1.0](https://github.com/svasek/homeassistant-neopool-modbus/compare/v6.0.0...v6.1.0) (2026-06-29)


### ✨ Features

* **config:** ✨ move options out of connection config flow ([#201](https://github.com/svasek/homeassistant-neopool-modbus/issues/201)) ([7538210](https://github.com/svasek/homeassistant-neopool-modbus/commit/753821086825f639d7fd8e0106b23d49a8eeb0d7))


### 🐛 Bug Fixes

* **hacs:** 🩹 raise minimum HA version to 2025.8.0 ([08c45ac](https://github.com/svasek/homeassistant-neopool-modbus/commit/08c45ac660fdbda952a8b49fbefc8dd957518ae4))
* **sensor:** 🐛 report 0 for hydrolysis/ionization production when filtration off ([#203](https://github.com/svasek/homeassistant-neopool-modbus/issues/203)) ([b1702cd](https://github.com/svasek/homeassistant-neopool-modbus/commit/b1702cdc7a58d2f21d79fcb37f87bdf78dfda6a0))

## [6.0.0](https://github.com/svasek/homeassistant-neopool-modbus/compare/v5.0.0...v6.0.0) (2026-06-20)


### ⚠ BREAKING CHANGES

* Timer start/stop entities moved from select.* to time.* domain. Any automations or scripts referencing select.filtration1_start, select.relay_aux1_start, etc. must be updated to the corresponding time.* entity IDs.

### ✨ Features

* 💥 move timer start/stop entities from select to time platform ([#195](https://github.com/svasek/homeassistant-neopool-modbus/issues/195)) ([6f8a10e](https://github.com/svasek/homeassistant-neopool-modbus/commit/6f8a10ea287deb86dc0930b2ea02e974a94c43ae))

## [5.0.0](https://github.com/svasek/homeassistant-neopool-modbus/compare/v4.1.2...v5.0.0) (2026-06-18)


### ⚠ BREAKING CHANGES

* 💥 drop slave_id and migrate entries to unit_id ([#194](https://github.com/svasek/homeassistant-neopool-modbus/issues/194))

### ✨ Features

* 💥 drop slave_id and migrate entries to unit_id ([#194](https://github.com/svasek/homeassistant-neopool-modbus/issues/194)) ([b6f3b94](https://github.com/svasek/homeassistant-neopool-modbus/commit/b6f3b94649767050443fa7001759c597c8184dcd))
* **config:** ✨ rename slave_id to unit_id (with legacy fallback) ([#188](https://github.com/svasek/homeassistant-neopool-modbus/issues/188)) ([ce738ed](https://github.com/svasek/homeassistant-neopool-modbus/commit/ce738ed58b522fd880abe8f468896a11aa5f7889))


### 🐛 Bug Fixes

* 🩹 tighten types, fix variable shadowing, use LightEntityDescription ([fe42a8a](https://github.com/svasek/homeassistant-neopool-modbus/commit/fe42a8a1c34c694af2e73fc9b98107cb0e696813))


### ♻️ Refactoring

* ♻️ delegate tier-1 logic to neopool-modbus library ([#190](https://github.com/svasek/homeassistant-neopool-modbus/issues/190)) ([8bac0bc](https://github.com/svasek/homeassistant-neopool-modbus/commit/8bac0bc0b773683217315bc686319be7a2ef10c5))
* ♻️ delegate tier-2 logic to neopool-modbus library ([#191](https://github.com/svasek/homeassistant-neopool-modbus/issues/191)) ([a35870f](https://github.com/svasek/homeassistant-neopool-modbus/commit/a35870f872be43a2c87a83c999da14f79a46bbbf))
* ♻️ migrate entity definitions to typed EntityDescription pattern ([#192](https://github.com/svasek/homeassistant-neopool-modbus/issues/192)) ([8e62592](https://github.com/svasek/homeassistant-neopool-modbus/commit/8e62592c81c95fb6cf0b903fd210a04fd47d11f9))
* ♻️ replace inline hex addresses with named register constants ([#193](https://github.com/svasek/homeassistant-neopool-modbus/issues/193)) ([c1add13](https://github.com/svasek/homeassistant-neopool-modbus/commit/c1add1348af063ffcd74cc2962b73267bde00ff1))

## [4.1.2](https://github.com/svasek/homeassistant-neopool-modbus/compare/v4.1.1...v4.1.2) (2026-06-15)


### 🐛 Bug Fixes

* 🐛 align with HA core pylint rules + RestoreSensor + i18n ([#185](https://github.com/svasek/homeassistant-neopool-modbus/issues/185)) ([cbb1bfb](https://github.com/svasek/homeassistant-neopool-modbus/commit/cbb1bfbcd162e6138ca6b192679daac7d5a85901))


### ♻️ Refactoring

* ♻️ tighten typing for HA core mypy strict (platinum tier) ([#187](https://github.com/svasek/homeassistant-neopool-modbus/issues/187)) ([8a76be0](https://github.com/svasek/homeassistant-neopool-modbus/commit/8a76be04f57e3c782c66c2c9754d13aca0c54e1b))

## [4.1.1](https://github.com/svasek/homeassistant-neopool-modbus/compare/v4.1.0...v4.1.1) (2026-06-14)


### 🐛 Bug Fixes

* 🐛 import platform constants from public API ([#184](https://github.com/svasek/homeassistant-neopool-modbus/issues/184)) ([9b7fd4f](https://github.com/svasek/homeassistant-neopool-modbus/commit/9b7fd4f1010fabac1ec49c53c1cdc6241da95aa9))


### ♻️ Refactoring

* **strings:** ♻️ adopt shared common strings and trim services.yaml ([#182](https://github.com/svasek/homeassistant-neopool-modbus/issues/182)) ([7106dfd](https://github.com/svasek/homeassistant-neopool-modbus/commit/7106dfda59041bdc737f56d11e4fa5044c305735))

## [4.1.0](https://github.com/svasek/homeassistant-neopool-modbus/compare/v4.0.1...v4.1.0) (2026-06-14)


### ✨ Features

* **sensor:** ✨ expose hydrolysis cell runtime counters and reset button ([#179](https://github.com/svasek/homeassistant-neopool-modbus/issues/179)) ([c5e53fe](https://github.com/svasek/homeassistant-neopool-modbus/commit/c5e53fe7a705c39bd8544d2fc6077b53d73f50ef)), closes [#177](https://github.com/svasek/homeassistant-neopool-modbus/issues/177)
* **services:** ✨ add read_register service ([#180](https://github.com/svasek/homeassistant-neopool-modbus/issues/180)) ([df045f1](https://github.com/svasek/homeassistant-neopool-modbus/commit/df045f100954dd88d5ceb18d4e3aec4a6cd25e52)), closes [#178](https://github.com/svasek/homeassistant-neopool-modbus/issues/178)

## [4.0.1](https://github.com/svasek/homeassistant-neopool-modbus/compare/v4.0.0...v4.0.1) (2026-06-10)


### 🐛 Bug Fixes

* 🐛 use COPY_TO_RTC_REGISTER constant for time sync writes ([#172](https://github.com/svasek/homeassistant-neopool-modbus/issues/172)) ([524b7b7](https://github.com/svasek/homeassistant-neopool-modbus/commit/524b7b7f94b2b8fbca25325a81f66fcf019e93da))
* **translations:** 🩹 align translation keys and add strings.json ([#167](https://github.com/svasek/homeassistant-neopool-modbus/issues/167)) ([4bbf645](https://github.com/svasek/homeassistant-neopool-modbus/commit/4bbf645c00ea0a8d35906f8f699eae1847afc525))


### ♻️ Refactoring

* ♻️ extract services to dedicated module and simplify coordinator ([#170](https://github.com/svasek/homeassistant-neopool-modbus/issues/170)) ([0b54268](https://github.com/svasek/homeassistant-neopool-modbus/commit/0b542687c3922d056575dced361489e03b33a9fe))

## [4.0.0](https://github.com/Svasek/homeassistant-vistapool-modbus/compare/v3.0.0...v4.0.0) (2026-06-07)


### ⚠ BREAKING CHANGES

* 💥 extract Modbus client into the new PyPI package ([#164](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/164))

### ✨ Features

* 💥 extract Modbus client into the new PyPI package ([#164](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/164)) ([caec35e](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/caec35ea8a290d9d407ba88882ced576f770b2c8))

## [3.0.0](https://github.com/Svasek/homeassistant-vistapool-modbus/compare/v2.1.0...v3.0.0) (2026-06-05)


### ⚠ BREAKING CHANGES

* 💥 rename domain to neopool with automatic entity migration ([#160](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/160))

### ✨ Features

* 💥 rename domain to neopool with automatic entity migration ([#160](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/160)) ([0552146](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/055214686164e5c1cdfa8dbdb2521ad78d20fca2))

## [2.1.0](https://github.com/Svasek/homeassistant-vistapool-modbus/compare/v2.0.0...v2.1.0) (2026-06-04)


### ✨ Features

* **sensor:** ✨ add filtration pump power and energy sensors ([#157](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/157)) ([db9e05f](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/db9e05fcc2821269c56496890a0134aa648393f0))


### 🐛 Bug Fixes

* **config:** 🐛 advanced options unlock password not matching device name ([#158](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/158)) ([59426a2](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/59426a27f29f0cb795092561813eee907fcaf82c))
* **translations:** 📝 add data_description to all config and options flow steps ([#154](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/154)) ([7d481f5](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/7d481f51200f21e5da124d08a0bcf19826b1e700))


### ♻️ Refactoring

* 🏷️ add strict type annotations across all modules ([#155](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/155)) ([1ec3ec2](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/1ec3ec2e9ef9fe5c4acb41a05f299792aeeb7c27))

## [2.0.0](https://github.com/Svasek/homeassistant-vistapool-modbus/compare/v1.26.2...v2.0.0) (2026-05-27)


### ⚠ BREAKING CHANGES

* Device and entity unique_ids now use hardware serial number instead of config entry_id. Existing installations will be migrated automatically, but entity IDs may change.

### ✨ Features

* 💥 stable device identity based on hardware serial number ([#146](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/146)) ([ba16e92](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/ba16e9241fcfb3c2b2fba0ec0b6c2c7c16d7f7da))


### 🐛 Bug Fixes

* **diagnostics:** 🔒️ use HA async_redact_data and remove data duplica… ([#147](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/147)) ([9fe5aef](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/9fe5aefc34261e80d3464dd60e1539928912b907))
* **helpers:** 🐛 handle cumulative relay speed bits for filtration ([#153](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/153)) ([3b9b747](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/3b9b7478583be08051eff4b6926a2388e0a30ecf)), closes [#152](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/152)


### ♻️ Refactoring

* ♻️ migrate from hass.data to runtime_data pattern ([#149](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/149)) ([bca8d0e](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/bca8d0ed3cac72b429c6e3e116b1a45e6a551ada))
* ♻️ migrate to repair issues and add parallel update limits ([#150](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/150)) ([ee140a2](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/ee140a21b2837eb5d21a58abad5dd1adf87ee6d0))
* ♻️ move entity icons and error messages to translation files ([#151](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/151)) ([fe28020](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/fe2802077b057f49f73ed76c180f15c75718d4a7))

## [1.26.2](https://github.com/Svasek/homeassistant-vistapool-modbus/compare/v1.26.1...v1.26.2) (2026-05-19)


### 🐛 Bug Fixes

* **config_flow:** 🩹 fix return type annotations and safe context access ([3bcf8d3](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/3bcf8d3579fa4c7dc5d9bcd57d90d3144b4b1997))


### 🎨 Style

* 💄 added icon images ([f642f01](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/f642f01bc63f80b84a90b5a8bc654f7e4fb63721))

## [1.26.1](https://github.com/Svasek/homeassistant-vistapool-modbus/compare/v1.26.0...v1.26.1) (2026-05-10)


### 🐛 Bug Fixes

* **binary_sensor:** 🐛 remove regulation out of range sensors ([126f8ea](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/126f8eab5a0267dfbf8911c6c30b590de2a85990))
* **number:** 🩹 extend pH setpoint range and add longer pump delay intervals ([940d059](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/940d059a8fafa68af61384c8705956fa0af363f7)), closes [#141](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/141)


### ♻️ Refactoring

* **select:** ♻️ unify select entities under mapped_register type ([#143](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/143)) ([699d23c](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/699d23c38620a340178a7208aae81891daaf2312))

## [1.26.0](https://github.com/Svasek/homeassistant-vistapool-modbus/compare/v1.25.0...v1.26.0) (2026-05-09)


### ✨ Features

* ✨ add write_register service and fix service registration ([#138](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/138)) ([55b36b7](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/55b36b73f9b59a9f34b39f4be4450af80a08e765))
* **binary_sensor:** ✨ add regulation out of range diagnostic sensor ([#140](https://github.com/Svasek/homeassistant-vistapool-modbus/issues/140)) ([9c1b702](https://github.com/Svasek/homeassistant-vistapool-modbus/commit/9c1b702b15bdfa3d6ce535c4202bd5fb27462fce))

## [1.25.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.24.0...v1.25.0) (2026-05-08)


### ✨ Features

* **coordinator:** ✨ add register integrity checks ([#134](https://github.com/svasek/homeassistant-vistapool-modbus/issues/134)) ([e6051e5](https://github.com/svasek/homeassistant-vistapool-modbus/commit/e6051e55e99dde813f3477f9f3af5abe5cd3027d))


### ♻️ Refactoring

* **modbus:** ♻️ replace hardcoded command register addresses with constants ([fe608ac](https://github.com/svasek/homeassistant-vistapool-modbus/commit/fe608acd113e8f6dd309ed0fd30185a439a8ea98))

## [1.24.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.23.0...v1.24.0) (2026-05-01)


### ✨ Features

* **sensor:** ✨ add dynamic relay GPIO mapping and pH pump status sensor ([#120](https://github.com/svasek/homeassistant-vistapool-modbus/issues/120)) ([977f5a4](https://github.com/svasek/homeassistant-vistapool-modbus/commit/977f5a45ba2158c253842ef2f64584038e2b9ba4))
* **sensor:** ✨ add filtration time remaining sensor ([#126](https://github.com/svasek/homeassistant-vistapool-modbus/issues/126)) ([2977072](https://github.com/svasek/homeassistant-vistapool-modbus/commit/29770721d05b38426b7af65d2be623dab86d2f02))


### 🐛 Bug Fixes

* 🐛 guard set_timer service removal with has_service check ([c2b8dca](https://github.com/svasek/homeassistant-vistapool-modbus/commit/c2b8dca7e7530a839ce3440d28da63d8d6646464))
* **modbus:** 🐛 skip filtration state fixup when INSTALLER page is stale ([3a2c07e](https://github.com/svasek/homeassistant-vistapool-modbus/commit/3a2c07ecbe4125eb21b97a270a3b6cdb51429f27)), closes [#122](https://github.com/svasek/homeassistant-vistapool-modbus/issues/122)
* **modbus:** 🩹 return False instead of {} in _perform_write_timer ([ea9ba7a](https://github.com/svasek/homeassistant-vistapool-modbus/commit/ea9ba7a49f2464cdf76e8da60c1383a86e3a5519))


### ♻️ Refactoring

* **binary_sensor:** ♻️ extract entity skip logic into helper function ([#125](https://github.com/svasek/homeassistant-vistapool-modbus/issues/125)) ([1980fbc](https://github.com/svasek/homeassistant-vistapool-modbus/commit/1980fbc772691c138d8d4390e8c62627eafdd3d7))
* **modbus:** ♻️ extract register read helper to reduce duplication ([#123](https://github.com/svasek/homeassistant-vistapool-modbus/issues/123)) ([2cea603](https://github.com/svasek/homeassistant-vistapool-modbus/commit/2cea6038e3906e152339b69e02e00f4f93da6b2f))
* **number:** ♻️ extract entity skip logic into helper function ([#129](https://github.com/svasek/homeassistant-vistapool-modbus/issues/129)) ([e750c90](https://github.com/svasek/homeassistant-vistapool-modbus/commit/e750c904a5a840a4aa1004cf2c83cd2cbd2fb9f6))
* **select:** ♻️ extract entity skip logic into helper function ([#130](https://github.com/svasek/homeassistant-vistapool-modbus/issues/130)) ([e34d608](https://github.com/svasek/homeassistant-vistapool-modbus/commit/e34d6082cc6c0f4040f69572d2ef17d1952bd552))
* **sensor:** ♻️ extract entity skip logic into helper function ([#128](https://github.com/svasek/homeassistant-vistapool-modbus/issues/128)) ([b51a50a](https://github.com/svasek/homeassistant-vistapool-modbus/commit/b51a50a24a7936d07c198d9a8adb3d14852584d8))
* **switch:** ♻️ extract entity skip logic into helper function ([#131](https://github.com/svasek/homeassistant-vistapool-modbus/issues/131)) ([29d3884](https://github.com/svasek/homeassistant-vistapool-modbus/commit/29d3884c8b3ab459fc62006414ec56754ce5e518))

## [1.23.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.22.1...v1.23.0) (2026-04-27)


### Features

* **sensor:** ♻️ revamp binary sensor naming and remove dead entities ([#118](https://github.com/svasek/homeassistant-vistapool-modbus/issues/118)) ([9c22ce1](https://github.com/svasek/homeassistant-vistapool-modbus/commit/9c22ce17c5ebffe7a25af608bf1f7b588fc3c100))

## [1.22.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.22.0...v1.22.1) (2026-04-26)


### Bug Fixes

* 🐛 gate entities on hardware module presence ([#116](https://github.com/svasek/homeassistant-vistapool-modbus/issues/116)) ([e99366f](https://github.com/svasek/homeassistant-vistapool-modbus/commit/e99366f37744b3d0c94123a41a121d6019698561))
* **helpers:** 🐛 read filtration speed from correct relay bits ([#113](https://github.com/svasek/homeassistant-vistapool-modbus/issues/113)) ([eb23b04](https://github.com/svasek/homeassistant-vistapool-modbus/commit/eb23b044e41379f516bd10c4da3cea0ad8e052c8)), closes [#112](https://github.com/svasek/homeassistant-vistapool-modbus/issues/112)
* **sensor:** 💥 merge polarity binary sensors into enum sensors ([#117](https://github.com/svasek/homeassistant-vistapool-modbus/issues/117)) ([b93ae6c](https://github.com/svasek/homeassistant-vistapool-modbus/commit/b93ae6cfa33e54498efd17dc1f9e537dc784d579))
* **sensor:** 🩹 derive ph alarm states from MBF_PH_STATUS register ([#115](https://github.com/svasek/homeassistant-vistapool-modbus/issues/115)) ([e3d7d45](https://github.com/svasek/homeassistant-vistapool-modbus/commit/e3d7d4558887fcc259f3d8cb73f27ebb40cef59b))

## [1.22.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.21.1...v1.22.0) (2026-04-17)


### Features

* ✨ add optimistic state updates with follow-up refresh for IO entities ([#109](https://github.com/svasek/homeassistant-vistapool-modbus/issues/109)) ([97b5470](https://github.com/svasek/homeassistant-vistapool-modbus/commit/97b54708331f8db26dbfc256829df4afa36b6323))

## [1.21.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.21.0...v1.21.1) (2026-04-16)


### Bug Fixes

* 🐛 Detect Besgo automatic valve via GPIO register ([#104](https://github.com/svasek/homeassistant-vistapool-modbus/issues/104)) ([19991dd](https://github.com/svasek/homeassistant-vistapool-modbus/commit/19991dd4acfdd80b927fcd4ae3bc06c23ee1725f))
* **const:** 🐛 lower MBF_PAR_HEATING_TEMP minimum from 10 °C to 0 °C ([225c257](https://github.com/svasek/homeassistant-vistapool-modbus/commit/225c25733bcc589cc2789b53e69b99835fd0b89b)), closes [#106](https://github.com/svasek/homeassistant-vistapool-modbus/issues/106)
* **modbus:** 🐛 fix binary_sensor.filtration_active incorrect in some installations ([#108](https://github.com/svasek/homeassistant-vistapool-modbus/issues/108)) ([37755b0](https://github.com/svasek/homeassistant-vistapool-modbus/commit/37755b0c582b9c1761f85bd974a7902e9d25ddaf))

## [1.21.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.20.1...v1.21.0) (2026-04-12)


### Features

* ✨ add UV lamp support with auto-detection ([#102](https://github.com/svasek/homeassistant-vistapool-modbus/issues/102)) ([e4d00c5](https://github.com/svasek/homeassistant-vistapool-modbus/commit/e4d00c519c72657de2f159f6f066c189b92fb7db))

## [1.20.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.20.0...v1.20.1) (2026-04-10)


### Bug Fixes

* 🔒️ validate timer name in set_timer service handler ([c328d55](https://github.com/svasek/homeassistant-vistapool-modbus/commit/c328d555643984aec6c59d572f96f30784043de1))
* **diagnostics:** 🔒️ redact host and port from diagnostic data ([11037e8](https://github.com/svasek/homeassistant-vistapool-modbus/commit/11037e89919915e42ee52361ce800908db3ee2f0))
* **entity:** 🛡️ guard against None coordinator data in device_info ([36521fa](https://github.com/svasek/homeassistant-vistapool-modbus/commit/36521fa344e6d34ce3831b49e795cff36b6658b8))
* **number:** 🐛 remove premature refresh before debounced write completes ([0382c59](https://github.com/svasek/homeassistant-vistapool-modbus/commit/0382c592e0023c163e8085ff592b803ea77cd457))


### Performance Improvements

* ⚡️ replace f-string logging with lazy % formatting ([5194ca2](https://github.com/svasek/homeassistant-vistapool-modbus/commit/5194ca2aedb32e57b7885e647c285897b57752dc))

## [1.20.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.19.0...v1.20.0) (2026-04-06)


### Features

* **button:** ✨ add backwash button and logic for automatic filtration valve ([#96](https://github.com/svasek/homeassistant-vistapool-modbus/issues/96)) ([0de93fe](https://github.com/svasek/homeassistant-vistapool-modbus/commit/0de93fe0e7b24077cbb32e6e7aee547d41cabeee))
* **config:** ✨ add default name localization for new devices ([d98cd9e](https://github.com/svasek/homeassistant-vistapool-modbus/commit/d98cd9e0a44ad085c4a2238167a269b110dee05b))
* **entity:** ✨detect and display machine name ([#98](https://github.com/svasek/homeassistant-vistapool-modbus/issues/98)) ([e0c60c4](https://github.com/svasek/homeassistant-vistapool-modbus/commit/e0c60c4a4934e7257320dc7d1394717721132166))
* **modbus:** ✨ notification based polling optimization ([#97](https://github.com/svasek/homeassistant-vistapool-modbus/issues/97)) ([244d555](https://github.com/svasek/homeassistant-vistapool-modbus/commit/244d55548d239c9925bbcdfab4b8c89efc06e9e2))


### Bug Fixes

* 🐛 update step value for redox setpoint ([5b146e8](https://github.com/svasek/homeassistant-vistapool-modbus/commit/5b146e8c44f70665b0efd0c176e3ae2605828953)), closes [#94](https://github.com/svasek/homeassistant-vistapool-modbus/issues/94)

## [1.19.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.18.3...v1.19.0) (2026-04-01)


### Features

* ✨ add filtration speed options for timers ([#92](https://github.com/svasek/homeassistant-vistapool-modbus/issues/92)) ([a04034d](https://github.com/svasek/homeassistant-vistapool-modbus/commit/a04034d644b8028cb0240691eb665788ba155adf))


### Bug Fixes

* 🐛 availability logic for filtration speed  and manual filtration ([a261836](https://github.com/svasek/homeassistant-vistapool-modbus/commit/a261836627da7d89f9a6279897f561c33453513c))

## [1.18.3](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.18.2...v1.18.3) (2026-03-20)


### Bug Fixes

* **select:** 🐛 backwash option writes to Modbus register ([#87](https://github.com/svasek/homeassistant-vistapool-modbus/issues/87)) ([7f58f4b](https://github.com/svasek/homeassistant-vistapool-modbus/commit/7f58f4ba9f6ce730ed0d3e7dffe5c7eb79336658))

## [1.18.2](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.18.1...v1.18.2) (2026-03-18)


### Bug Fixes

* **coordinator:** 🐛 mark entities unavailable on Modbus communication error ([#84](https://github.com/svasek/homeassistant-vistapool-modbus/issues/84)) ([13d6b5d](https://github.com/svasek/homeassistant-vistapool-modbus/commit/13d6b5db834dec9e2eb4cdd39673e92bb5fc2b72))
* **modbus:** 🐛 filter FC20 broadcast frames to prevent Modbus TCP failures ([#83](https://github.com/svasek/homeassistant-vistapool-modbus/issues/83)) ([edb82d1](https://github.com/svasek/homeassistant-vistapool-modbus/commit/edb82d1373ae418f904bd5f9b2c405450a4379f7))

## [1.18.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.18.0...v1.18.1) (2026-03-12)


### Bug Fixes

* add use_cover_sensor toggle to guard cover-related entities ([9dac041](https://github.com/svasek/homeassistant-vistapool-modbus/commit/9dac0412213da870ed71c7d0c2fae01feb3aa846))
* use SelectSelector for scan_interval and timer_resolution ([d4576bb](https://github.com/svasek/homeassistant-vistapool-modbus/commit/d4576bbd49f72785714bf3f7fd0dd808311d2c8f))

## [1.18.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.17.0...v1.18.0) (2026-03-05)


### Features

* ✨ add reconfigure flow to update connection settings ([#78](https://github.com/svasek/homeassistant-vistapool-modbus/issues/78)) ([a721d30](https://github.com/svasek/homeassistant-vistapool-modbus/commit/a721d30026866b98653718e3beb5770f6bf6569b))

## [1.17.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.16.0...v1.17.0) (2026-03-04)


### Features

* ✨ Hydrolysis cover reduction & temperature shutdown controls ([#73](https://github.com/svasek/homeassistant-vistapool-modbus/issues/73)) ([00dfa9c](https://github.com/svasek/homeassistant-vistapool-modbus/commit/00dfa9cffac90822703f76abd493dcc852127b71))


### Bug Fixes

* 🐛 handle case where both HIDRO keys are absent ([8aaf09d](https://github.com/svasek/homeassistant-vistapool-modbus/commit/8aaf09d8826a38264cc21c15635c2727e51ff2aa))

## [1.16.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.15.1...v1.16.0) (2026-03-04)


### Features

* ✨ add Winter Mode to suspend during off-season ([#75](https://github.com/svasek/homeassistant-vistapool-modbus/issues/75)) ([dab8508](https://github.com/svasek/homeassistant-vistapool-modbus/commit/dab8508ee6d9629cb8586406213da0adc93ca13d))

## [1.15.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.15.0...v1.15.1) (2026-03-03)


### Bug Fixes

* ⏪ revert invalid 'pH' unit from pH entities ([44027b8](https://github.com/svasek/homeassistant-vistapool-modbus/commit/44027b8aede5f77e4f34a7e16f32a08dcef13ba1)), closes [#60](https://github.com/svasek/homeassistant-vistapool-modbus/issues/60) [#59](https://github.com/svasek/homeassistant-vistapool-modbus/issues/59)

## [1.15.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.14.0...v1.15.0) (2026-03-02)


### Features

* ✨ add Modbus framer selection (TCP vs RTU over TCP) ([#70](https://github.com/svasek/homeassistant-vistapool-modbus/issues/70)) ([ed6a845](https://github.com/svasek/homeassistant-vistapool-modbus/commit/ed6a84542dd9be47e94a883ea80159e8dde7e52d))


### Bug Fixes

* 🐛 address Copilot code review findings from previous PRs ([#71](https://github.com/svasek/homeassistant-vistapool-modbus/issues/71)) ([4b21c37](https://github.com/svasek/homeassistant-vistapool-modbus/commit/4b21c37dcbcb2b32eb0a9fa12b8bf8d17f562eeb))

## [1.14.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.13.2...v1.14.0) (2026-03-01)


### Features

* **binary_sensor:** ✨ add Pool Cover sensor ([#65](https://github.com/svasek/homeassistant-vistapool-modbus/issues/65)) ([915e3ca](https://github.com/svasek/homeassistant-vistapool-modbus/commit/915e3caade00bbfc23e5bb88af0eb18297491e51)), closes [#58](https://github.com/svasek/homeassistant-vistapool-modbus/issues/58)


### Bug Fixes

* 🐛 code review fixes for HA 2026.2 compatibility ([#69](https://github.com/svasek/homeassistant-vistapool-modbus/issues/69)) ([2491d0f](https://github.com/svasek/homeassistant-vistapool-modbus/commit/2491d0f861befdd16b10474d874479cbcb23b14d))
* 🐛 correct hydrolysis intensity unit determination logic ([#64](https://github.com/svasek/homeassistant-vistapool-modbus/issues/64)) ([61ba9de](https://github.com/svasek/homeassistant-vistapool-modbus/commit/61ba9de23f0686b0ee5084c2f968f42376014df9))
* **sensor:** 🔧 update icons for filtration modes ([006ceca](https://github.com/svasek/homeassistant-vistapool-modbus/commit/006ceca98d563ae1a9ae67ea2640d57d65b7bde8))

## [1.13.2](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.13.1...v1.13.2) (2026-02-05)


### Bug Fixes

* 🐛 remove redundant entity_id assignment in component classes ([1778567](https://github.com/svasek/homeassistant-vistapool-modbus/commit/177856729ee9f74ac9a242c63195051b95a0762c)), closes [#61](https://github.com/svasek/homeassistant-vistapool-modbus/issues/61)

## [1.13.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.13.0...v1.13.1) (2026-02-05)


### Bug Fixes

* **sensor defs:** 🔧 set unit for pH measurement ([#60](https://github.com/svasek/homeassistant-vistapool-modbus/issues/60)) ([6d21ec8](https://github.com/svasek/homeassistant-vistapool-modbus/commit/6d21ec84cb8cb2776e3f526822782b75a0a4d2b8)), closes [#59](https://github.com/svasek/homeassistant-vistapool-modbus/issues/59)

## [1.13.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.12.1...v1.13.0) (2025-10-21)


### Features

* **sensor:** ✨ add intelligent mode intervals sensor ([fa98d8c](https://github.com/svasek/homeassistant-vistapool-modbus/commit/fa98d8c55c783faa92eaa8a82e648015580f87b0))
* **sensor:** ✨ add intelligent mode next interval sensor ([b73e8c3](https://github.com/svasek/homeassistant-vistapool-modbus/commit/b73e8c3416a91b5f503ba09112a2ef60f6b3a839))


### Bug Fixes

* **coordinator:** 🔧 handle simultaneous setpoint changes and initial sync ([79fbbfd](https://github.com/svasek/homeassistant-vistapool-modbus/commit/79fbbfda04baefc9930c7dab279c4c61bc6fecec))
* **sensor:** 🔧 skip temperature sensor when not detected ([b0cb16a](https://github.com/svasek/homeassistant-vistapool-modbus/commit/b0cb16adb8efbc1d459ea858ff3d24d824901644))

## [1.12.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.12.0...v1.12.1) (2025-10-20)


### Bug Fixes

* **translations:** 🔧 correct phrasing in Czech and Spanish translations ([6ec1871](https://github.com/svasek/homeassistant-vistapool-modbus/commit/6ec18711532200f69c45e52c8d87334557d181f4))

## [1.12.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.11.0...v1.12.0) (2025-10-17)


### Features

* ✨ add climate mode switch functionality ([98c2c9c](https://github.com/svasek/homeassistant-vistapool-modbus/commit/98c2c9ce00086d628a35b143bce20b8896463487))
* ✨ add heating and intelligent setpoint synchronization ([937d414](https://github.com/svasek/homeassistant-vistapool-modbus/commit/937d414555518311dc2425836c776aa0d771df29))
* ✨ add intelligent minimum filtration time support ([6709354](https://github.com/svasek/homeassistant-vistapool-modbus/commit/67093548bb52ab75bc95d56e5534453611c6f878))
* ✨ add smart temperature and antifreeze features ([ea923e3](https://github.com/svasek/homeassistant-vistapool-modbus/commit/ea923e3c5cbb3338cefcd0d3b6cf137fe91ef7ed)), closes [#50](https://github.com/svasek/homeassistant-vistapool-modbus/issues/50)

## [1.11.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.10.1...v1.11.0) (2025-09-04)


### Features

* **modbus:** ✨ add compatibility helpers for pymodbus addressing ([bc3cfc4](https://github.com/svasek/homeassistant-vistapool-modbus/commit/bc3cfc48dbb99ff32d22ec91044bf69f320950cf))


### Bug Fixes

* **modbus:** 🐛 improve error handling by raising ModbusException ([ecc7ab0](https://github.com/svasek/homeassistant-vistapool-modbus/commit/ecc7ab0151cb9130ad3c5a4b5d103bb4028ff6b2))

## [1.10.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.10.0...v1.10.1) (2025-08-15)


### Bug Fixes

* **modbus:** 🐛 correct register indices for power module data retrieval ([d93b969](https://github.com/svasek/homeassistant-vistapool-modbus/commit/d93b969620664758913afefb5f3ce6b75171917d))
* **modbus:** 🐛 validate AUX relay index before writing state ([e28d708](https://github.com/svasek/homeassistant-vistapool-modbus/commit/e28d7087110693ea7ec7f8511bbf5d0e6a7568f8))

## [1.10.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.9.0...v1.10.0) (2025-08-10)


### Features

* **select:** ✨ Add pH pump activation delay feature ([a613494](https://github.com/svasek/homeassistant-vistapool-modbus/commit/a613494a0e82e8896945e3db17200e502902bdcd))


### Bug Fixes

* 🐛 correct typos, redundancies and formating ([471bb18](https://github.com/svasek/homeassistant-vistapool-modbus/commit/471bb1867ff5f5b550d777242dad360414d7556f))
* **coordinator:** 🐛 ensure config_entry is passed to DataUpdateCoordinator ([a461cf1](https://github.com/svasek/homeassistant-vistapool-modbus/commit/a461cf18e0d87a9dac2f35c3845b64d7dcc29645))
* **number:** 🐛 optimize value retrieval using coordinator cache ([46c05de](https://github.com/svasek/homeassistant-vistapool-modbus/commit/46c05de1c3f9139ebf618e6ce736c3bc4488e327))

## [1.9.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.8.4...v1.9.0) (2025-07-20)


### Features

* **coordinator:** ✨ improve update interval handling and error management ([04b8c49](https://github.com/svasek/homeassistant-vistapool-modbus/commit/04b8c4943308bee1685ef44fd0c1a65c9e904f00))
* **modbus:** ✨ add diagnostics tracking and error handling metrics ([7c1dfc6](https://github.com/svasek/homeassistant-vistapool-modbus/commit/7c1dfc61e14a56f15f78bbe8759c405e938c4f03))

## [1.8.4](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.8.3...v1.8.4) (2025-07-19)


### Bug Fixes

* **modbus:** 🩹 ensure consistent return values in async_write_register ([bfbe8d1](https://github.com/svasek/homeassistant-vistapool-modbus/commit/bfbe8d1919540c9eedb1e123565dc4c0f612322c))
* **number:** 🩹 improve logging during entity addition ([08fb3ad](https://github.com/svasek/homeassistant-vistapool-modbus/commit/08fb3ad8afa61521af9344ef5592ee269b515ca6))
* **sensor:** 🩹 streamline filtration speed checks and icon mapping ([a1be07f](https://github.com/svasek/homeassistant-vistapool-modbus/commit/a1be07f96f6358a3c2ca91e3b851852fedef2d3a))

## [1.8.3](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.8.2...v1.8.3) (2025-07-18)


### Bug Fixes

* **binary_sensor:** 🩹 improve device status handling for binary sensors ([dcd4e36](https://github.com/svasek/homeassistant-vistapool-modbus/commit/dcd4e36a4ecde59ca4bf4947696e258445343c4f))
* **diagnostics:** 🩹 handle missing coordinator in diagnostics retrieval ([f2c5fab](https://github.com/svasek/homeassistant-vistapool-modbus/commit/f2c5fab5ad8a39be47e7199b979156f44b2c9253))
* **modbus:** 🩹 improve connection handling and diagnostics ([9fffdb9](https://github.com/svasek/homeassistant-vistapool-modbus/commit/9fffdb9c22b1f0f9ccb7a7a7f0e358a14321d544))

## [1.8.2](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.8.1...v1.8.2) (2025-07-09)


### Bug Fixes

* **light, number, select, switch:** 🐛 handle missing Modbus client ([5e42b0c](https://github.com/svasek/homeassistant-vistapool-modbus/commit/5e42b0cf3ec5e705d940f4e0b23f50a9f151f44a))

## [1.8.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.8.0...v1.8.1) (2025-06-30)


### Bug Fixes

* **entity:** 🐛 update suggested_object_id to use device_slug ([b7c0cd4](https://github.com/svasek/homeassistant-vistapool-modbus/commit/b7c0cd474e7d7ef5567129339afcfe6fa0781607))

## [1.8.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.7.5...v1.8.0) (2025-06-30)


### Features

* **config,options:** ✨ add new options for enabling filtration timers in the configuration ([75a46cb](https://github.com/svasek/homeassistant-vistapool-modbus/commit/75a46cbd824689a9dffbb615c43e667e8e3ee073))

## [1.7.5](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.7.4...v1.7.5) (2025-06-23)


### Bug Fixes

* **binary_sensor:** 🐛 update default enabled state for sensors ([7d81822](https://github.com/svasek/homeassistant-vistapool-modbus/commit/7d818226fd1fa9800aaa9b903788fb0af64f432e))

## [1.7.4](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.7.3...v1.7.4) (2025-06-20)


### Bug Fixes

* **modbus:** 🩹 improve client closure handling for unstable Modbus connections ([81f33cf](https://github.com/svasek/homeassistant-vistapool-modbus/commit/81f33cf3d21487b2b59890729684798fb51def3e))
* **sensor:** 🐛 update pH level unit to None for consistency ([3ca6b0b](https://github.com/svasek/homeassistant-vistapool-modbus/commit/3ca6b0b81eb31cdb24c57bd176021024a475e1c6))

## [1.7.3](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.7.2...v1.7.3) (2025-06-20)


### Bug Fixes

* **sensor:** 🩹 add option to measure values when filtration is off ([51fc55f](https://github.com/svasek/homeassistant-vistapool-modbus/commit/51fc55f3aacb43bc068cb32497eaf7530f2cf7eb))

## [1.7.2](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.7.1...v1.7.2) (2025-06-19)


### Bug Fixes

* **sensor:** 🩹 enhance sensor definitions with device and state classes ([c55a15f](https://github.com/svasek/homeassistant-vistapool-modbus/commit/c55a15f93d9ca228c76fa640df2f07f1bc0bd6d5))

## [1.7.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.7.0...v1.7.1) (2025-06-19)


### Bug Fixes

* **sensor:** 🐛 prevent stale sensor values when filtration is off ([cddd3d3](https://github.com/svasek/homeassistant-vistapool-modbus/commit/cddd3d3985d83a06d3e83ed061c20b550a1cf60e))

## [1.7.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.6.0...v1.7.0) (2025-06-19)


### Features

* **binary_sensor, sensor:** ✨ enhance sensor availability based on filtration state ([188ad35](https://github.com/svasek/homeassistant-vistapool-modbus/commit/188ad3559819c28057013fc2f9f342e27622e522))


### Bug Fixes

* **setup:** 🐛 skip setup if no data from Modbus ([c4ca493](https://github.com/svasek/homeassistant-vistapool-modbus/commit/c4ca49357673e71575b3857029fadaefe4fca581))

## [1.6.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.5.1...v1.6.0) (2025-06-19)


### Features

* **config_flow:** ✨ Added asynchronous host and port validation in the config flow ([de5f0fb](https://github.com/svasek/homeassistant-vistapool-modbus/commit/de5f0fbd6b253539f080799c6b9cb7142ef80083))


### Bug Fixes

* **binary_sensor, select, sensor:** 🐛 disable certain entities by default ([be7cca5](https://github.com/svasek/homeassistant-vistapool-modbus/commit/be7cca5895dc35bc98a0050a9ec16e5664d9dc90))

## [1.5.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.5.0...v1.5.1) (2025-06-18)


### Bug Fixes

* **modbus:** 🐛 ensure close method is callable before invoking ([6870501](https://github.com/svasek/homeassistant-vistapool-modbus/commit/6870501968fd301bccd8b4243412f08defe239d3))

## [1.5.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.4.0...v1.5.0) (2025-06-18)


### Features

* **light:** ✨ changed pool light from switch to light entity ([4666d21](https://github.com/svasek/homeassistant-vistapool-modbus/commit/4666d211a8a5e32f6b2b64e4879806e2c81cd0ed))
* **modbus:** ✨ persistent TCP client, reconnect and safe close ([cfac5c6](https://github.com/svasek/homeassistant-vistapool-modbus/commit/cfac5c660bc3caf0fc04e59e4639d5697350c7f4))


### Bug Fixes

* **coordinator:** 🐛 add support for enabling/disabling timers in coordinator ([abc6c2e](https://github.com/svasek/homeassistant-vistapool-modbus/commit/abc6c2ef3d1f5daac85e4d8802e78a8f02b66e81))
* **coordinator:** 🐛 handle Modbus communication errors gracefully ([d7972f2](https://github.com/svasek/homeassistant-vistapool-modbus/commit/d7972f2ad7ee50470df052aa1b498c15310c255b))
* **modbus:** 🐛 improve client closing logic for Modbus connection ([f075caf](https://github.com/svasek/homeassistant-vistapool-modbus/commit/f075cafc8c74bfc6985c52ef4da9a13a5c8fa16e))

## [1.4.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.3.0...v1.4.0) (2025-06-17)


### Features

* **options:** ✨ add timer resolution and update scan interval descriptions ([d83053d](https://github.com/svasek/homeassistant-vistapool-modbus/commit/d83053d499a6f3f5157ab5c9425dac298978dfa1))
* **relays:** ✨ Add timer functionality for AUX and Light relays ([#27](https://github.com/svasek/homeassistant-vistapool-modbus/issues/27)) ([89c312b](https://github.com/svasek/homeassistant-vistapool-modbus/commit/89c312b90c675a0418e3f219e92caefc2e912e5b))

## [1.3.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.2.5...v1.3.0) (2025-06-15)


### Features

* **options:** ✨ add advanced options for enabling 'Backwash' mode ([9993931](https://github.com/svasek/homeassistant-vistapool-modbus/commit/99939316b815c09539d93a304a93870ee2fddda5))
* **options:** ✨ enhance options flow with automatic integration reload ([02d1e21](https://github.com/svasek/homeassistant-vistapool-modbus/commit/02d1e215a825ff28c4094e16d14293e86a53639e))

## [1.2.5](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.2.4...v1.2.5) (2025-06-11)


### Bug Fixes

* **binary_sensor:** 🛠️ skip acid pump if relay is not assigned ([89e7529](https://github.com/svasek/homeassistant-vistapool-modbus/commit/89e752964c3fe193d6c3ed628a43730db540154d))

## [1.2.4](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.2.3...v1.2.4) (2025-06-06)


### Bug Fixes

* **timer:** 🐛 pad timer registers to ensure correct parsing ([4d12a1c](https://github.com/svasek/homeassistant-vistapool-modbus/commit/4d12a1ceec68bd78a522a2d780dd6411dd9cba4e))

## [1.2.3](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.2.2...v1.2.3) (2025-06-03)


### Bug Fixes

* **modbus:** 🐛 add connection error handling for Modbus client ([e429430](https://github.com/svasek/homeassistant-vistapool-modbus/commit/e4294303703ef031e7a966967a97d357fd7b5c8f))

## [1.2.2](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.2.1...v1.2.2) (2025-05-30)


### Bug Fixes

* **manifest:** 🐛 Fixed integration version ([ebab4c1](https://github.com/svasek/homeassistant-vistapool-modbus/commit/ebab4c10e40d22db028f2e12ba198184be73512c))

## [1.2.1](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.2.0...v1.2.1) (2025-05-29)


### Bug Fixes

* **select:** ✨ show/hide boost mode select based on model support ([9cca2ef](https://github.com/svasek/homeassistant-vistapool-modbus/commit/9cca2efc646a96d635f659b70fa9471ae243125f))

## [1.2.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.1.0...v1.2.0) (2025-05-29)


### Features

* **filtration:** ✨ add filtration speed functionality controll for devices which support it ([5aed83c](https://github.com/svasek/homeassistant-vistapool-modbus/commit/5aed83c9322b07da889eb83a06f09cadbc5683e8))

## [1.1.0](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.0.3...v1.1.0) (2025-05-28)


### Features

* **boost:** ✨ add boost mode functionality and translations ([62617d5](https://github.com/svasek/homeassistant-vistapool-modbus/commit/62617d59997b21ec607b57b57f4285c3a60771c3))
* **button:** ✨ add "Clear Errors" button functionality and translations ([b07dfe9](https://github.com/svasek/homeassistant-vistapool-modbus/commit/b07dfe9ea9f6e65291c8257c13d524a32199af11))
* **sensor:** ✨ add filtration speed sensor and update translations ([cf5b51f](https://github.com/svasek/homeassistant-vistapool-modbus/commit/cf5b51f1f1e34182b21e2debb9b14c9b3f45883f))

## [1.0.3](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.0.2...v1.0.3) (2025-05-26)


### Bug Fixes

* **modbus:** 🐛 Fixed InvalidStateError ([102ebf9](https://github.com/svasek/homeassistant-vistapool-modbus/commit/102ebf9f95e4a478e184f35127955f39779fab7e))

## [1.0.2](https://github.com/svasek/homeassistant-vistapool-modbus/compare/v1.0.1...v1.0.2) (2025-05-25)


### Bug Fixes

* **manifest:** 🐛 Fixed documentation and issue tracker URLs ([7f23704](https://github.com/svasek/homeassistant-vistapool-modbus/commit/7f237046b293dc5054b310ef845430289ed352da))
