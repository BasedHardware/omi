import * as React from 'react';
import { Button, Pressable, Text, TextInput, View } from 'react-native';
import { Theme } from '../../theme';
import { FlashList } from '@shopify/flash-list';
import { Country, countries } from '../../utils/countries';
import { useRouter } from '../../routing';
import { useRoute } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';

const Row = React.memo((props: { item: Country, callback: (item: Country) => void }) => {
    return (
        <Pressable style={(props) => ({ opacity: props.pressed ? 0.3 : 1 })} onPress={() => props.callback(props.item)}>
            <View style={{ height: 44, alignItems: 'center', paddingHorizontal: 16, flexDirection: 'row' }}>
                <Text style={{ flexGrow: 1, flexBasis: 0, paddingRight: 16, fontSize: 16 }}>{props.item.emoji} {props.item.label}</Text>
                <Text style={{ fontSize: 17, color: Theme.textSecondary }}>{props.item.value}</Text>
            </View>
        </Pressable>
    );
});

const ListDivider = <View style={{ paddingHorizontal: 16, height: 0.5, flexDirection: 'row' }}><View style={{ flexGrow: 1, height: 0.5, backgroundColor: Theme.divider }} /></View>;

export const CountryPicker = React.memo(() => {
    let router = useRouter();
    let params = useRoute().params as { callback: (item: Country) => void, current: Country };
    let [filter, setFilter] = React.useState('');
    let data = React.useMemo(() => {

        // Check if filtering enabled
        let query = filter.trim().toLocaleLowerCase();
        if (query.length === 0) {
            return countries;
        }

        // Filter
        const res: Country[] = [];
        for (let c of countries) {
            if (c.label.toLocaleLowerCase().startsWith(query) || c.value.startsWith(query) || c.value.startsWith('+' + query)) {
                res.push(c);
            }
        }
        return res;
    }, [filter]);
    return (
        <View style={{ flexGrow: 1, alignSelf: 'stretch', alignItems: 'stretch', backgroundColor: Theme.background, flexDirection: 'column' }}>
            <View style={{ paddingHorizontal: 8, flexDirection: 'row', alignItems: 'center', backgroundColor: '#F2F2F2', height: 54 }}>
                <View style={{ flexGrow: 1, flexBasis: 0, backgroundColor: '#E3E3E3', borderRadius: 8, paddingLeft: 8, height: 36, marginTop: 4, flexDirection: 'row' }}>
                    <Ionicons name="search" size={20} color="#8D8D8F" style={{ marginTop: 8 }} />
                    <TextInput
                        style={{ flexGrow: 1, flexBasis: 0, borderRadius: 8, paddingLeft: 6, paddingRight: 12, height: 36, fontSize: 17 }}
                        placeholder='Search'
                        placeholderTextColor="#8D8D8F"
                        autoFocus={true}
                        value={filter}
                        onChangeText={setFilter}
                    />
                </View>
                <View style={{ paddingTop: 4, paddingLeft: 4 }}>
                    <Button title='Cancel' onPress={() => router.goBack()} color={Theme.accent} />
                </View>
            </View>
            <View style={{ height: 0.5, backgroundColor: Theme.divider }} />
            <FlashList<Country>
                renderItem={({ item }) => <Row item={item} callback={(i) => {
                    params.callback(i);
                    router.goBack();
                }} />}
                ItemSeparatorComponent={() => ListDivider}
                ListFooterComponent={data.length > 0 ? () => ListDivider : null}
                data={data}
                estimatedItemSize={48}
                keyboardDismissMode='on-drag'
                keyboardShouldPersistTaps="handled"
            />
        </View>
    );
});