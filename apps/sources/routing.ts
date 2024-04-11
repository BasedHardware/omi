import { NavigationProp, useNavigation } from "@react-navigation/native";

export function useRouter() {
    return useNavigation<NavigationProp<any>>();
}