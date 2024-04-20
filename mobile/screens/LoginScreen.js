import { useEffect, useState } from 'react';
import { View, StyleSheet } from 'react-native';
import { Input, Button, Icon } from 'react-native-elements';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { v4 as uuidv4 } from 'uuid';
import * as SecureStore from 'expo-secure-store';

const Stack = createNativeStackNavigator();

const LoginTab = ({ navigation }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');

    const handleLogin = () => {
        // Implement Firebase Auth
    };

    useEffect(() => {
        // Set user state data
    }, []);

    return (
        <View style={styles.container}>
            <Input
                placeholder="Username"
                leftIcon={{ type: 'font-awesome', name: 'user-o' }}
                onChangeText={(text) => setUsername(text)}
                value={username}
                containerStyle={styles.formInput}
                leftIconContainerStyle={styles.formIcon}
            />
            <Input
                placeholder="Password"
                leftIcon={{ type: 'font-awesome', name: 'key' }}
                onChangeText={(text) => setPassword(text)}
                value={password}
                containerStyle={styles.formInput}
                leftIconContainerStyle={styles.formIcon}
            />
            <View style={styles.formButton}>
                <Button
                    onPress={() => handleLogin()}
                    icon={
                        <Icon
                            name="sign-in"
                            type="font-awesome"
                            color="#fff"
                            iconStyle={{ marginRight: 10 }}
                            buttonStyle={{ backgroundColor: '#5637DD' }}
                        />
                    }
                    title="Login"
                    color="#5637DD"
                />
            </View>
            <Button
                title="Go to Register"
                onPress={() => navigation.navigate('Register')}
            />
        </View>
    );
};

const RegisterTab = ({ navigation }) => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [firstname, setFirstname] = useState('');
    const [lastname, setLastname] = useState('');
    const [email, setEmail] = useState('');

    const handleRegister = async () => {
        const userId = uuidv4(); // Generates a unique user ID
        const userInfo = {
            username,
            password, // Consider encrypting the password or using a secure authentication method
            firstname,
            lastname,
            email,
        };

        try {
            await SecureStore.setItemAsync(userId, JSON.stringify(userInfo));
            console.log('User registered with ID:', userId);
            // Optionally, navigate to the login screen or directly log the user in
        } catch (error) {
            console.error('Error storing the user info', error);
        }
    };

    return (
        <View style={styles.container}>
            <Input
                placeholder="Username"
                leftIcon={{ type: 'font-awesome', name: 'user-o' }}
                onChangeText={(text) => setUsername(text)}
                value={username}
                containerStyle={styles.formInput}
                leftIconContainerStyle={styles.formIcon}
            />
            <Input
                placeholder="Password"
                leftIcon={{ type: 'font-awesome', name: 'key' }}
                onChangeText={(text) => setPassword(text)}
                value={password}
                containerStyle={styles.formInput}
                leftIconContainerStyle={styles.formIcon}
            />
            <Input
                placeholder="First Name"
                leftIcon={{ type: 'font-awesome', name: 'user-o' }}
                onChangeText={(text) => setFirstname(text)}
                value={firstname}
                containerStyle={styles.formInput}
                leftIconContainerStyle={styles.formIcon}
            />
            <Input
                placeholder="Last Name"
                leftIcon={{ type: 'font-awesome', name: 'user-o' }}
                onChangeText={(text) => setLastname(text)}
                value={lastname}
                containerStyle={styles.formInput}
                leftIconContainerStyle={styles.formIcon}
            />
            <Input
                placeholder="Email"
                leftIcon={{ type: 'font-awesome', name: 'envelope-o' }}
                onChangeText={(text) => setEmail(text)}
                value={email}
                containerStyle={styles.formInput}
                leftIconContainerStyle={styles.formIcon}
            />
            <View style={styles.formButton}>
                <Button
                    onPress={() => handleRegister()}
                    title="Register"
                    color="#5637DD"
                    icon={
                        <Icon
                            name="user-plus"
                            type="font-awesome"
                            color="#fff"
                            iconStyle={{ marginRight: 10 }}
                            buttonStyle={{ backgroundColor: '#5637DD' }}
                        />
                    }
                />
            </View>
            <Button title="Back to Login" onPress={() => navigation.goBack()} />
        </View>
    );
};

const AuthScreen = () => {
    return (
        <Stack.Navigator initialRouteName="Login">
            <Stack.Screen
                name="Login"
                component={LoginTab}
                options={{ headerShown: false }}
            />
            <Stack.Screen
                name="Register"
                component={RegisterTab}
                options={{ headerShown: false }}
            />
        </Stack.Navigator>
    );
};

const styles = StyleSheet.create({
    container: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        margin: 10,
    },
    formIcon: {
        marginRight: 10,
    },
    formInput: {
        padding: 8,
        height: 60,
    },
    formCheckbox: {
        margin: 8,
        backgroundColor: null,
    },
    formButton: {
        margin: 20,
        marginRight: 40,
        marginLeft: 40,
    },
    imageContainer: {
        flex: 1,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-evenly',
        margin: 10,
    },
    image: {
        width: 60,
        height: 60,
    },
});

export default AuthScreen;
