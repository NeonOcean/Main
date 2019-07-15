import copy
import json
import os
import abc
import typing

from NeonOcean.Main import Debug, Paths, This
from NeonOcean.Main.Saving import SectionStandard
from NeonOcean.Main.Tools import Exceptions, Types, Version

class Persistent(abc.ABC):
	"""
	A class for handling persistent data. This is an incomplete class, you would need to implement the load and save functions.
	"""

	class Value:
		def __init__ (self, value: typing.Any, valueType: type, default: typing.Any, verify: typing.Callable, isSet: bool):
			"""
			Used for storage of persistent data.
			"""

			self.Value = value  # type: typing.Any
			self.ValueType = valueType  # type: type
			self.Default = default  # type: typing.Any
			self.Verify = verify  # type: typing.Callable
			self._isSet = isSet  # type: bool

		def IsSet (self) -> bool:
			return self._isSet

		def Save (self) -> typing.Any:
			return copy.deepcopy(self.Value)

		def Get (self) -> typing.Any:
			return copy.deepcopy(self.Value)

		def Set (self, value, version: Version.Version, verify: bool = True) -> None:
			if verify:
				copiedValue = copy.deepcopy(self.Verify(value, version))  # type: typing.Any
			else:
				copiedValue = copy.deepcopy(value)  # type: typing.Any

			self.Value = copiedValue

		def Reset (self) -> None:
			self.Value = self.Default
			self._isSet = False

		def Commit (self) -> None:
			self._isSet = True

	def __init__ (self, currentVersion: Version.Version, hostNamespace: str = This.Mod.Namespace, alwaysSaveValues: bool = False):
		"""
		:param currentVersion: The current version of what ever will be controlling this persistence object.
							   This value can allow you to correct outdated persistent data.
		:type currentVersion: Version.Version
		:param hostNamespace: Errors made by this persistent object will show up under this namespace.
		:type hostNamespace: str
		:param alwaysSaveValues: If this value is true this persistence object will save all values. Otherwise this object will not save values that have not been
		set or were reset at some point.
		:type alwaysSaveValues: bool
		"""

		if not isinstance(currentVersion, Version.Version):
			raise Exceptions.IncorrectTypeException(currentVersion, "currentVersion", (Version.Version,))

		if not isinstance(hostNamespace, str):
			raise Exceptions.IncorrectTypeException(hostNamespace, "hostNamespace", (str,))

		self.CurrentVersion = currentVersion  # type: Version.Version
		self.HostNamespace = hostNamespace  # type: str


		self._loadedData = dict()  # type: typing.Dict[str, typing.Any]
		self._loadedLastVersion = None  # type: typing.Optional[Version.Version]

		self._alwaysSaveValues = alwaysSaveValues  # type: bool

		self._storage = dict()  # type: typing.Dict[str, Persistent.Value]
		self._updateStorage = list()  # type: list

		self._loadCallbacks = list()  # type: list
		self._saveCallbacks = list()  # type: list

	@property
	def LoadedLastVersion (self) -> typing.Optional[Version.Version]:
		"""
		The last version the loaded data was loaded in.
		:return:
		"""

		if self._loadedLastVersion is None:
			return None

		return Version.Version(str(self._loadedLastVersion))

	@abc.abstractmethod
	def Load (self, *args, **kwargs) -> typing.Any:
		raise NotImplementedError()

	@abc.abstractmethod
	def Save (self, *args, **kwargs) ->  typing.Any:
		raise NotImplementedError()

	def Setup (self, key: str, valueType: type, default, verify: typing.Callable) -> None:
		"""
		Setup persistent data for this persistence object. All persistent data must be setup before it can be used. Persistent data can be loaded before being
		setup but will remain dormant until setup. Persistent data also cannot be setup twice, an exception will be raised if this is tried.

		:param key: The name of the persistent data to be setup. This will be used to get and set the value in the future and is case sensitive.
		:type key: str

		:param valueType: The persistent data's value type, i.e. str, bool, float. The value of this persistent data should never be anything other than this type.
		There no functionality to verify that the value type is parse able, bad values may work fine but cause saving to fail.
		:type valueType: type

		:param default: The persistent data's default value. Needs to be of the type specified in the valueType parameter.

		:param verify: This is called when changing or loading a value to verify that is correct and still valid.
					   Verify functions need to take two parameters: the value being verified and the version the value was set.
					   The first parameter will always be of the type specified in the 'valueType'. The value will often not be the current value of the persistent data.
					   The second parameter will be the version this value was set. The type of this parameter will be NeonOcean.Main.Tools.Version.Version
					   Verify functions should also return the input or a corrected value.
					   If the value cannot be corrected the verify function should raise an exception, the persistent data may then revert to its default if necessary.
		:type verify: typing.Callable

		:rtype: None
		"""

		if not isinstance(key, str):
			raise Exceptions.IncorrectTypeException(key, "key", (str,))

		if self.IsSetup(key):
			raise Exception("Persistent data '" + key + "' is already setup.")

		if not isinstance(valueType, type):
			raise Exceptions.IncorrectTypeException(valueType, "valueType", (type,))

		if not isinstance(default, valueType):
			raise Exceptions.IncorrectTypeException(default, "default", (valueType,))

		if not isinstance(verify, typing.Callable):
			raise Exceptions.IncorrectTypeException(verify, "verify", ("Callable",))

		try:
			verifiedDefault = verify(default)
		except Exception as e:
			raise ValueError("Failed to verify default value for persistent data '" + key + "'.") from e

		if verifiedDefault != default:
			Debug.Log("Verification of default value for persistent data '" + key + "' changed it.", self.HostNamespace, level = Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)

		version = self.LoadedLastVersion

		if version is None:
			version = self.CurrentVersion

		if key in self._loadedData:
			value = self._loadedData[key]

			try:
				value = verify(value, version)
			except Exception:
				Debug.Log("Verify callback found fault with the value that was stored for persistent data '" + key + "'.", self.HostNamespace, Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)
				value = verifiedDefault

			self._storage[key] = self.Value(value, valueType, default, verify, True)
		else:
			self._storage[key] = self.Value(verifiedDefault, valueType, default, verify, False)


	def IsSetup (self, key: str) -> bool:
		"""
		Returns true if the persistent data specified by the key is setup.

		:param key: The name of the persistent data, is case sensitive.
		:type key: str
		:rtype: bool
		"""

		return key in self._storage

	def Get (self, key: str):
		"""
		Gets the value of the persistent data specified by the key. The value returned will be a deep copy of what is stored, modifying it should never change
		anything unless you set it with the set function.

		:param key: The name of the persistent data, is case sensitive.
		:type key: str
		:return: The return object will always be of the type specified for the target persistent data during setup.
		"""

		if not isinstance(key, str):
			raise Exceptions.IncorrectTypeException(key, "key", (str,))

		if not self.IsSetup(key):
			raise Exception("Persistent data '" + key + "' is not setup.")

		return self._storage[key].Get()

	def Set (self, key: str, value, autoSave: bool = True, autoUpdate: bool = True) -> None:
		"""
		Set the value of the persistent data specified by the key. The value is deep copied before being but into storage, modifying the value after setting
		it will not change the stored version.

		:param key: The name of the persistent data, is case sensitive.
		:type key: str
		:param value: The value the persistent data will be changing to. This must be of the type specified for the target persistent data during setup.
		:param autoSave: Whether or not to automatically save the persistent data after changing the value.
		 				 This can allow you to change multiple values at once without saving each time.
		:type autoSave: bool
		:param autoUpdate: Whether or not to automatically notify callbacks to the fact that a value has changed.
						   This can allow you to change multiple values at once without calling update callbacks each time.
		:type autoUpdate: bool
		:rtype: None
		"""

		if not isinstance(key, str):
			raise Exceptions.IncorrectTypeException(key, "key", (str,))

		if not self.IsSetup(key):
			raise Exception("Persistent data '" + key + "' is not setup.")

		valueStorage = self._storage[key]

		if not isinstance(value, valueStorage.ValueType):
			raise Exceptions.IncorrectTypeException(value, "value", (valueStorage.ValueType,))

		if not isinstance(autoSave, bool):
			raise Exceptions.IncorrectTypeException(autoSave, "autoSave", (bool,))

		if not isinstance(autoUpdate, bool):
			raise Exceptions.IncorrectTypeException(autoUpdate, "autoUpdate", (bool,))

		valueStorage.Set(value, self.CurrentVersion)

		if autoSave:
			self.Save()

		if autoUpdate:
			self.Update()

	def ValueIsSet (self, key: str) -> bool:
		"""
		Get whether or not this key's value has been set, an exception will be raised it the key has not been setup.

		:param key: The name of the persistent data, is case sensitive.
		:type key: str
		:return: True if the value has been set, False if not.
		:rtype: bool
		"""

		if not self.IsSetup(key):
			raise Exception("Persistent data '" + key + "' is not setup.")

		valueStorage = self._storage[key]  # type: Persistent.Value
		return valueStorage.IsSet()

	def Reset (self, key: str = None, autoSave: bool = True, autoUpdate: bool = True) -> None:
		"""
		Resets persistent data to its default value.

		:param key: The name of the persistent data, is case sensitive. If the key is none, all values will be reset.
		:type key: str
		:param autoSave: Whether or not to automatically save the persistent data after resetting the values.
		:type autoSave: bool
		:param autoUpdate: Whether or not to automatically notify callbacks to the fact that the values have been reset.
		:type autoUpdate: bool
		:rtype: None
		"""

		if not isinstance(key, str) and key is not None:
			raise Exceptions.IncorrectTypeException(key, "key", (str,))

		if key is None:
			for valueStorage in self._storage.values():  # type: str, Persistent.Value
				valueStorage.Reset()
		else:
			if not self.IsSetup(key):
				raise Exception("Persistent data '" + key + "' is not setup.")

			valueStorage = self._storage[key]  # type: Persistent.Value
			valueStorage.Reset()

		if autoSave:
			self.Save()

		if autoUpdate:
			self.Update()

	def CommitValue (self, key: str = None) -> None:
		"""
		If the value isn't set to be saved this will make it be saved. Normally this object will not write values that have not been set or were reset at
		some point.
		:param key: The name of the persistent data, is case sensitive. If the key is none, all values will be committed.
		:type key: str
		"""

		if key is None:
			for valueStorage in self._storage:  # type: Persistent.Value
				valueStorage.Commit()
		else:
			valueStorage = self._storage.get(key)  # type: Persistent.Value

			if valueStorage is not None:
				valueStorage.Commit()

	def Update (self) -> None:
		"""
		Calls all update functions listening to this persistence object.
		This should be called after any persistent data change where you elected not to allow for auto-updating.

		:rtype: None
		"""

		for callback in self._updateStorage:  # type: typing.Callable
			callback()

	def RegisterUpdate (self, update: typing.Callable) -> None:
		"""
		Register an update callback function to this persistence object.
		Updates should be called any time any value is changed.

		:param update: Update callbacks must take no parameters.
		:type update: typing.Callable
		:rtype: None
		"""

		if not isinstance(update, typing.Callable):
			raise Exceptions.IncorrectTypeException(update, "update", ("Callable",))

		self._updateStorage.append(update)

	def UnregisterUpdate (self, update: typing.Callable) -> None:
		"""
		Removes a update callback from the registry.

		:param update: The callback targeted for removal.
		:type update: typing.Callable
		:rtype: None
		"""

		if not isinstance(update, typing.Callable):
			raise Exceptions.IncorrectTypeException(update, "update", ("Callable",))

		if update in self._updateStorage:
			self._updateStorage.remove(update)

	def RegisterLoadCallback (self, callback: typing.Callable) -> None:
		"""
		Register an a load callback function to this persistence object.
		These callbacks should be called any time the load method is called.

		:param callback: Load callbacks must take no parameters.
		:type callback: typing.Callable
		:rtype: None
		"""

		if not isinstance(callback, typing.Callable):
			raise Exceptions.IncorrectTypeException(callback, "callback", ("Callable",))

		self._loadCallbacks.append(callback)

	def UnregisterLoadCallback (self, callback: typing.Callable) -> None:
		"""
		Removes a load callback from the registry.

		:param callback: Load callbacks must take no parameters.
		:type callback: typing.Callable
		:rtype: None
		"""

		if not isinstance(callback, typing.Callable):
			raise Exceptions.IncorrectTypeException(callback, "callback", ("Callable",))

		if callback in self._loadCallbacks:
			self._loadCallbacks.remove(callback)

	def _LoadSetData (self, persistentData: dict, lastVersion: typing.Optional[Version.Version] = None) -> bool:
		"""
		:param persistentData: The persistent data to be loaded. This should just be a dictionary with every key paired with its value.
		:type persistentData: dict
		:param lastVersion: The last version this data was saved successfully in.
		:type lastVersion: Version.Version
		:return: True if this completed without incident, False if not.
		:rtype: bool
		"""

		operationSuccess = True  # type: bool

		changed = False

		for persistentKey in list(persistentData.keys()):  # type: str
			persistentValue = persistentData[persistentKey]  # type: typing.Any

			if not isinstance(persistentKey, str):
				Debug.Log("Invalid type in persistent data.\n" + Exceptions.GetIncorrectTypeExceptionText(persistentKey, "PersistentData<Key>", (str,)), self.HostNamespace, Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)
				persistentData.pop(persistentKey, None)
				changed = True
				operationSuccess = False
				continue

			if not persistentKey in self._storage:
				continue

			valueStorage = self._storage[persistentKey]  # type: Persistent.Value

			if not isinstance(persistentValue, valueStorage.ValueType):
				Debug.Log("Invalid type in persistent data.\n" + Exceptions.GetIncorrectTypeExceptionText(persistentKey, "PersistentData[%s]" % persistentKey, (valueStorage.ValueType,)), self.HostNamespace, Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)
				persistentData.pop(persistentKey, None)
				changed = True
				operationSuccess = False
				continue

			try:
				valueStorage.Set(persistentValue, lastVersion)
			except Exception:
				Debug.Log("Cannot set value '" + str(persistentValue) + "' for persistent data '" + persistentKey + "'.", self.HostNamespace, Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)
				persistentData.pop(persistentKey, None)
				changed = True
				operationSuccess = False
				continue

		self._loadedData = persistentData
		self._loadedLastVersion = lastVersion

		if changed:
			self.Save()

		self.Update()

		return operationSuccess

	def _SaveGetData (self) -> typing.Tuple[bool, dict]:
		"""
		:return: The first value indicates if this method completed without incident. The second is the save data.
		:rtype: typing.Tuple[bool, dict]
		"""

		operationSuccess = True  # type: bool

		persistentData = copy.deepcopy(self._loadedData)  # type: typing.Dict[str, typing.Any]

		for persistentKey, persistentValueStorage in self._storage.items():  # type: str, Persistent.Value
			try:
				if self._alwaysSaveValues or persistentValueStorage.IsSet:
					persistentData[persistentKey] = persistentValueStorage.Save()
			except Exception:
				Debug.Log("Failed to save value of '" + persistentKey + "'. This entry may be reset the next time this persistent data is loaded.", self.HostNamespace, Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)
				persistentData.pop(persistentKey, None)
				operationSuccess = False

		return operationSuccess, persistentData

	def _ActivateLoadCallbacks (self):
		for loadCallback in self._loadCallbacks:  # type: typing.Callable
			try:
				loadCallback()  # type: bool
			except:
				Debug.Log("Failed to activate load callback at '" + Types.GetFullName(loadCallback) + "'.", self.HostNamespace, Debug.LogLevels.Exception, group = self.HostNamespace, owner = __name__)

class PersistentDirect(Persistent):
	"""
	A class for handling persistent data. This version will allow you to directly input the persistent data container when using the load method, and get the persistent
	data container as the return value when using the save method.
	"""

	_valuesKey = "Values"
	_lastVersionKey = "LastVersion"

	def Load (self, persistentDataContainer: dict) -> bool:
		"""
		Load persistent data from a persistent data container.
		:param persistentDataContainer: The persistent data container dictionary.
		:type persistentDataContainer: dict
		:rtype: None
		"""

		operationSuccess = True  # type: bool

		if not isinstance(persistentDataContainer, dict):
			raise Exceptions.IncorrectTypeException(persistentDataContainer, "persistentDataContainer", (dict,))

		persistentData = persistentDataContainer.get(self._valuesKey, dict())  # type: typing.Dict[str, typing.Any]

		if not isinstance(persistentData, dict):
			Debug.Log("Invalid type in persistent data container.\n" + Exceptions.GetIncorrectTypeExceptionText(persistentData, "PersistentDataContainer[%s]" % self._valuesKey, (dict,)), self.HostNamespace, Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)
			persistentData = dict()
			operationSuccess = False

		lastVersionString = persistentDataContainer.get(self._lastVersionKey)  # type:

		if lastVersionString is None:
			lastVersion = None
		else:
			if not isinstance(lastVersionString, str):
				Debug.Log("Invalid type in persistent data container.\n" + Exceptions.GetIncorrectTypeExceptionText(lastVersionString, "PersistentDataContainer[%s]" % self._lastVersionKey, (dict,)), self.HostNamespace, Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)
				lastVersion = None
				operationSuccess = False
			else:
				try:
					lastVersion = Version.Version(lastVersionString)
				except Exception:
					Debug.Log("Cannot convert persistent data's last version value '" + lastVersionString + "' to a version number object", self.HostNamespace, Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)
					lastVersion = None
					operationSuccess = False

		self.Reset(autoSave = False, autoUpdate = False)
		setDataSuccess = self._LoadSetData(persistentData, lastVersion = lastVersion)  # type: bool

		self._ActivateLoadCallbacks()

		if not setDataSuccess:
			return False

		return operationSuccess

	def Save (self) -> typing.Tuple[bool, dict]:
		"""
		Creates and returns a persistent data container with the current data.

		:return: The first value indicates if this method completed without incident. The second is the save data.
		:rtype: typing.Tuple[bool, dict]
		"""

		getDataSuccess, persistentData = self._SaveGetData()  # type: bool, dict

		persistentDataContainer = {
			self._valuesKey: persistentData,
			self._lastVersionKey: str(self.CurrentVersion)
		}

		return getDataSuccess, persistentDataContainer

class PersistentJson(PersistentDirect):
	"""
	A class for handling persistent data. This version will allow you to directly input the persistent data as a json string when using the load method, and get the string
	as the return value when using the save method.
	"""

	def Load (self, persistentDataContainerString: str, *args) -> bool:
		"""
		Load persistent data from the file path specified when initiating this object, if it exists.
		:param persistentDataContainerString: The persistent data container dictionary as a json encoded string.
		:type persistentDataContainerString: str
		:rtype: None
		"""

		operationSuccess = True  # type: bool

		if not isinstance(persistentDataContainerString, str):
			raise Exceptions.IncorrectTypeException(persistentDataContainerString, "persistentDataContainerString", (str,))

		try:
			persistentDataContainer = json.JSONDecoder().decode(persistentDataContainerString)
		except Exception:
			Debug.Log("Could not decode the persistent data container string.", self.HostNamespace, Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)
			persistentDataContainer = { }

		if not isinstance(persistentDataContainer, dict):
			Debug.Log("Could not convert persistent data container string to a dictionary.", self.HostNamespace, Debug.LogLevels.Warning, group = self.HostNamespace, owner = __name__)
			persistentDataContainer = { }

		loadSuccessful = super().Load(persistentDataContainer)  # type: bool

		if not loadSuccessful:
			return False

		return operationSuccess

	def Save (self) -> typing.Tuple[bool, str]:
		"""
		Encodes the persistent data container to a json string. This method can handle cases in which any persistent data's key or value cannot be encoded.

		:return: The first value indicates if this method completed without incident. The second is the save data.
		:rtype: typing.Tuple[bool, dict]
		"""

		operationSuccess = True  # type: bool

		saveSuccess, persistentDataContainer = super().Save()  # type: bool, dict

		persistentData = persistentDataContainer[self._valuesKey]  # type: dict
		persistentDataValuesString = ""  # type: str

		for persistentKey, persistentValue in persistentData.items():  # type: str, typing.Any
			keyInformation = "Key: " + persistentKey  # type: str

			try:
				assert isinstance(persistentKey, str)
				persistentKeyString = json.JSONEncoder(indent = "\t").encode(persistentKey)  # type: str
				assert "\n" not in persistentKeyString and "\r" not in persistentKeyString
			except Exception:
				Debug.Log("Failed to encode a persistence key to a json string.\n" + keyInformation, self.HostNamespace, Debug.LogLevels.Exception, group = self.HostNamespace, owner = __name__)
				operationSuccess = False
				continue

			valueInformation = "Value Type: " + Types.GetFullName(persistentKey) + "\nValue Value: " + persistentKey  # type: str

			try:
				persistentValueString = json.JSONEncoder(indent = "\t").encode(persistentValue)  # type: str
			except Exception:
				Debug.Log("Failed to encode a persistence value to a json string.\n" + keyInformation + "\n" + valueInformation, self.HostNamespace, Debug.LogLevels.Exception, group = self.HostNamespace, owner = __name__)
				operationSuccess = False
				continue

			persistentValueString = persistentValueString.replace("\n", "\n\t\t")

			if persistentDataValuesString != "":
				persistentDataValuesString += ",\n"

			persistentDataValuesString += "\t\t" + persistentKeyString + ": " + persistentValueString

		persistentDataString = "\t\"" + self._valuesKey + "\": {"  # type: str

		if persistentDataValuesString != "":
			persistentDataString += "\n" + persistentDataValuesString + "\n\t}"
		else:
			persistentDataString += "}"

		lastVersion = persistentDataContainer[self._lastVersionKey]  # type: str

		try:
			lastVersionString = "\t\"" + self._lastVersionKey + "\": " + json.JSONEncoder(indent = "\t").encode(lastVersion)  # type: str
		except Exception as e:
			raise Exception("Failed to encode a persistence last version to a json string.") from e

		persistentDataContainerString = "{\n" + persistentDataString + ",\n" + lastVersionString + "\n}"  # type: str

		if not saveSuccess:
			return False, persistentDataContainerString

		return operationSuccess, persistentDataContainerString

class PersistentFile(PersistentJson):
	"""
	A class for handling persistent data. This version will read and write the data to a file through the load and save methods.
	"""

	def __init__ (self, filePath: str, currentVersion: Version.Version, hostNamespace: str = This.Mod.Namespace, alwaysSaveValues: bool = False):
		"""
		:param filePath: The file path this persistence object will be written to and read from.
		:type filePath: str
		:param currentVersion: The current version of what ever will be controlling this persistence object.
							   This value can allow you to correct outdated persistent data.
		:type currentVersion: Version.Version
		:param hostNamespace: Errors made by this persistent object will show up under this namespace.
		:type hostNamespace: str
		:param alwaysSaveValues: If this value is true this persistence object will save all values. Otherwise this object will not save values that have not been
		set or were reset at some point.
		:type alwaysSaveValues: bool
		"""

		if not isinstance(filePath, str):
			raise Exceptions.IncorrectTypeException(filePath, "path", (str,))

		super().__init__(currentVersion, hostNamespace = hostNamespace, alwaysSaveValues = alwaysSaveValues)

		self.FilePath = filePath  # type: str

	def Load (self, *args) -> bool:
		"""
		Load persistent data from the file path specified when initiating this object, if it exists.
		:rtype: None
		"""

		operationSuccess = True  # type: bool

		persistentDataContainerString = "{}"  # type: str

		if os.path.exists(self.FilePath):
			try:
				with open(self.FilePath) as persistentFile:
					persistentDataContainerString = persistentFile.read()
			except Exception:
				Debug.Log("Failed to read from '" + Paths.StripUserDataPath(self.FilePath) + "'.", self.HostNamespace, Debug.LogLevels.Error, group = self.HostNamespace, owner = __name__)

		loadSuccessful = super().Load(persistentDataContainerString)  # type: bool

		if not loadSuccessful:
			return False

		return operationSuccess

	def Save (self) -> bool:
		"""
		Saves the currently stored persistent data to the file path specified when initiating this object.
		If the directory the save file is in doesn't exist one will be created.
		:rtype: None
		"""

		operationSuccess = True  # type: bool

		saveSuccessful, persistentDataContainerString = super().Save()  # type: bool, str

		try:
			if not os.path.exists(os.path.dirname(self.FilePath)):
				os.makedirs(os.path.dirname(self.FilePath))

			with open(self.FilePath, mode = "w+") as persistentFile:
				persistentFile.write(persistentDataContainerString)
		except Exception:
			Debug.Log("Failed to read to '" + Paths.StripUserDataPath(self.FilePath) + "'.", self.HostNamespace, Debug.LogLevels.Error, group = self.HostNamespace, owner = __name__)
			operationSuccess = False

		if not saveSuccessful:
			return False

		return operationSuccess

class PersistentSection(PersistentDirect):
	"""
	A class for writing branched persistent data to a branched saving section.
	"""

	def __init__ (self, linkedSection: SectionStandard.SectionStandard, sectionKey: str, currentVersion: Version.Version, hostNamespace: str = This.Mod.Namespace):
		"""
		:param linkedSection: The section this persistence object is linked to.
		:type linkedSection: SectionStandard.SectionStandard
		:param sectionKey: The key the persistent data is saved to and loaded from in the section data.
		:type sectionKey: str
		:param currentVersion: The current version of what ever will be controlling this persistence object.
							   This value can allow you to correct outdated persistent data.
		:type currentVersion: Version.Version
		:param hostNamespace: Errors made by this persistent object will show up under this namespace.
		:type hostNamespace: str
		"""

		self._linkedSection = linkedSection
		self._sectionKey = sectionKey

		self._linkedSection.RegisterLoadCallback(self._SectionLoadCallback)
		self._linkedSection.RegisterSaveCallback(self._SectionSaveCallback)
		self._linkedSection.RegisterResetCallback(self._SectionResetCallback)

		super().__init__(currentVersion, hostNamespace = hostNamespace)

	@property
	def LinkedSection (self) -> SectionStandard.SectionStandard:
		return self._linkedSection

	@property
	def SectionKey (self) -> str:
		return self._sectionKey

	def _SectionLoadCallback (self, section: SectionStandard.SectionStandard) -> bool:
		persistentDataContainer = {
			self._valuesKey: section.GetValue(self.SectionKey),
			self._lastVersionKey: section.SavingObject.DataHostVersion
		}  # type: dict

		loadSuccessful = self.Load(persistentDataContainer = persistentDataContainer)  # type: bool
		return loadSuccessful

	def _SectionSaveCallback (self, section: SectionStandard.SectionStandard) -> bool:
		saveSuccessful, persistentDataContainer = self.Save()  # type: bool, dict
		section.Set(self.SectionKey, persistentDataContainer[self._valuesKey])

		return saveSuccessful

	def _SectionResetCallback (self, section: SectionStandard.SectionStandard) -> bool:
		persistentDataContainer = {
			self._valuesKey: section.GetValue(self.SectionKey),
			self._lastVersionKey: section.SavingObject.DataHostVersion
		}

		loadSuccessful = self.Load(persistentDataContainer = persistentDataContainer)  # type: bool
		return loadSuccessful

