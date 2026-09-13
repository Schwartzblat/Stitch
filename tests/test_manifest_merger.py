import lxml.etree
import pytest

from conftest import android, build_element, build_manifest, build_module_apk
from stitch import manifest_merger


def test_activity_declared_in_module_is_extracted():
    module = build_manifest('<application><activity android:name="com.mod.Main"/></application>')

    components = manifest_merger.extract_components(module, 'com.mod')

    assert [element.tag for element in components.application] == ['activity']
    assert components.application[0].get(android('name')) == 'com.mod.Main'


def test_root_level_permissions_features_and_queries_are_extracted():
    module = build_manifest(
        '<uses-permission android:name="android.permission.INTERNET"/>'
        '<uses-permission-sdk-23 android:name="android.permission.CAMERA"/>'
        '<uses-feature android:name="android.hardware.camera"/>'
        '<queries><package android:name="com.other.app"/></queries>'
        '<application/>'
    )

    components = manifest_merger.extract_components(module, 'com.mod')

    assert [element.tag for element in components.root] == [
        'uses-permission', 'uses-permission-sdk-23', 'uses-feature', 'queries'
    ]


def test_uses_sdk_is_not_extracted():
    """The host's minSdk/targetSdk must survive; a module's <uses-sdk> would override them."""
    module = build_manifest('<uses-sdk android:minSdkVersion="28"/><application/>')

    components = manifest_merger.extract_components(module, 'com.mod')

    assert components.root == []


def test_relative_component_name_is_resolved_against_module_package():
    """A leading-dot name is relative to the module's package; left as-is it is a ClassNotFoundException in the host."""
    module = build_manifest('<application><activity android:name=".Settings"/></application>', package='com.mod')

    components = manifest_merger.extract_components(module, 'com.mod')

    assert components.application[0].get(android('name')) == 'com.mod.Settings'


def test_relative_target_activity_of_alias_is_resolved():
    module = build_manifest(
        '<application><activity-alias android:name=".Alias" android:targetActivity=".Settings"/></application>',
        package='com.mod',
    )

    components = manifest_merger.extract_components(module, 'com.mod')

    assert components.application[0].get(android('targetActivity')) == 'com.mod.Settings'


def test_module_resource_reference_attribute_is_dropped():
    """Stitch injects dex and libs but never resources.arsc, so a @7f ref points at a table that is not in the output."""
    module = build_manifest(
        '<application><activity android:name="com.mod.Main" android:label="@7f0d001d"/></application>'
    )

    components = manifest_merger.extract_components(module, 'com.mod')

    assert android('label') not in components.application[0].attrib


def test_module_resource_reference_on_nested_element_is_dropped():
    module = build_manifest(
        '<application><activity android:name="com.mod.Main">'
        '<meta-data android:name="cfg" android:resource="@7f100000"/>'
        '</activity></application>'
    )

    components = manifest_merger.extract_components(module, 'com.mod')

    assert android('resource') not in components.application[0].find('meta-data').attrib


def test_module_attribute_reference_is_dropped():
    module = build_manifest(
        '<application><activity android:name="com.mod.Main" android:theme="?7f040011"/></application>'
    )

    components = manifest_merger.extract_components(module, 'com.mod')

    assert android('theme') not in components.application[0].attrib


def test_framework_resource_reference_is_kept():
    """Package id 0x01 is a framework resource; it exists on-device regardless of the host's resource table."""
    module = build_manifest(
        '<application><activity android:name="com.mod.Main" android:theme="@1030010"/></application>'
    )

    components = manifest_merger.extract_components(module, 'com.mod')

    assert components.application[0].get(android('theme')) == '@1030010'


def test_tools_namespace_attributes_are_stripped():
    """`tools:` attributes are build-time only and the host manifest declares no tools namespace."""
    module = build_manifest(
        '<application><activity android:name="com.mod.Main" tools:ignore="MissingClass" tools:replace="android:name"/>'
        '</application>'
    )

    components = manifest_merger.extract_components(module, 'com.mod')

    assert list(components.application[0].attrib) == [android('name')]


INTENT_FILTER = '<intent-filter><action android:name="android.intent.action.MAIN"/></intent-filter>'


def test_component_with_intent_filter_and_no_exported_is_rejected():
    """Android 12+ refuses to install such a component; failing here beats failing on the user's device."""
    module = build_manifest(f'<application><activity android:name="com.mod.Main">{INTENT_FILTER}</activity></application>')

    with pytest.raises(ValueError, match='com.mod.Main'):
        manifest_merger.extract_components(module, 'com.mod')


def test_component_with_intent_filter_and_explicit_exported_is_accepted():
    module = build_manifest(
        f'<application><activity android:name="com.mod.Main" android:exported="true">{INTENT_FILTER}</activity>'
        '</application>'
    )

    components = manifest_merger.extract_components(module, 'com.mod')

    assert components.application[0].get(android('exported')) == 'true'


def test_module_components_are_appended_to_the_host_application():
    host = build_manifest('<application><activity android:name="com.host.Main"/></application>', package='com.host')
    components = manifest_merger.ModuleComponents(
        application=[build_element('<application><activity android:name="com.mod.Settings"/></application>')[0]],
        root=[],
    )

    manifest_merger.merge_components(host, components)

    assert [element.get(android('name')) for element in host.find('application')] == [
        'com.host.Main', 'com.mod.Settings'
    ]


def test_module_root_elements_are_appended_to_the_host_manifest():
    host = build_manifest('<application/>', package='com.host')
    components = manifest_merger.ModuleComponents(
        application=[],
        root=[build_element('<uses-permission android:name="android.permission.INTERNET"/>')],
    )

    manifest_merger.merge_components(host, components)

    assert [element.get(android('name')) for element in host.findall('uses-permission')] == [
        'android.permission.INTERNET'
    ]


def test_component_already_declared_in_the_host_is_not_added_twice():
    """ExternalModule.invoke_line already injects the provider; the module manifest may declare the same one."""
    host = build_manifest(
        '<application><provider android:name="com.mod.InitProvider"/></application>', package='com.host'
    )
    components = manifest_merger.ModuleComponents(
        application=[build_element(
            '<application><provider android:name="com.mod.InitProvider" android:exported="false"/></application>'
        )[0]],
        root=[],
    )

    manifest_merger.merge_components(host, components)

    assert len(host.find('application').findall('provider')) == 1


def test_provider_whose_authority_collides_with_the_host_is_not_added():
    """Two providers sharing an authority make the package uninstallable."""
    host = build_manifest(
        '<application><provider android:name="com.host.Existing" android:authorities="com.mod.init"/></application>',
        package='com.host',
    )
    components = manifest_merger.ModuleComponents(
        application=[build_element(
            '<application><provider android:name="com.mod.InitProvider" android:authorities="com.mod.init"/>'
            '</application>'
        )[0]],
        root=[],
    )

    manifest_merger.merge_components(host, components)

    assert [element.get(android('name')) for element in host.find('application').findall('provider')] == [
        'com.host.Existing'
    ]


def test_permission_already_requested_by_the_host_is_not_added_twice():
    host = build_manifest(
        '<uses-permission android:name="android.permission.INTERNET"/><application/>', package='com.host'
    )
    components = manifest_merger.ModuleComponents(
        application=[],
        root=[build_element('<uses-permission android:name="android.permission.INTERNET"/>')],
    )

    manifest_merger.merge_components(host, components)

    assert len(host.findall('uses-permission')) == 1


def test_components_are_read_from_a_built_module_apk(tmp_path):
    apk = build_module_apk(
        tmp_path / 'module.apk',
        '<uses-permission android:name="android.permission.INTERNET"/>'
        '<application><activity android:name=".Main" android:exported="false"/></application>',
    )

    components = manifest_merger.collect_components(apk)

    assert components.application[0].get(android('name')) == 'com.mod.Main'
    assert components.root[0].get(android('name')) == 'android.permission.INTERNET'


def test_relative_name_without_a_module_package_is_rejected():
    """AGP can omit package= from the manifest; silently producing 'None.Main' would fail only at runtime."""
    module = lxml.etree.fromstring(
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
        '<application><activity android:name=".Main"/></application></manifest>'
    )

    with pytest.raises(ValueError, match='package'):
        manifest_merger.extract_components(module, None)


def test_module_package_is_read_from_the_apk(tmp_path):
    apk = build_module_apk(tmp_path / 'module.apk', '<application/>', package='com.example.mod')

    assert manifest_merger.read_package(apk) == 'com.example.mod'
