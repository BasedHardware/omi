import {useContext, useRef} from 'react';
import {ListItem} from 'react-native-elements';
import Swipeable from 'react-native-gesture-handler/Swipeable';
import {TouchableOpacity, StyleSheet} from 'react-native';
import {ChatContext} from '../../contexts/ChatContext';
import {FontAwesomeIcon} from '@fortawesome/react-native-fontawesome';
import {faTrash} from '@fortawesome/free-solid-svg-icons';

const ChatListItem = ({item, onItemPress}) => {
  const swipeableRef = useRef(null);
  const touchableRef = useRef(null);
  const {deleteChat} = useContext(ChatContext);

  const handleDelete = item => {
    if (swipeableRef.current) {
      swipeableRef.current.close();
    }

    deleteChat(item.chatId);
  };

  const renderRightActions = () => (
    <TouchableOpacity
      onPress={() => handleDelete(item)}
      style={styles.deleteButton}>
      <FontAwesomeIcon icon={faTrash} size={30} color="white" />
    </TouchableOpacity>
  );

  return (
    <Swipeable
      ref={swipeableRef}
      renderRightActions={renderRightActions}
      friction={2}
      rightThreshold={100}
      simultaneousHandlers={touchableRef}>
      <TouchableOpacity
        ref={touchableRef}
        onPress={() => onItemPress(item)}
        activeOpacity={0.6}
        style={styles.touchable}>
        <ListItem key={item.id} bottomDivider containerStyle={styles.listItem}>
          <ListItem.Content>
            <ListItem.Title>{item.chat_name}</ListItem.Title>
            <ListItem.Subtitle>{item.model}</ListItem.Subtitle>
          </ListItem.Content>
          <ListItem.Chevron />
        </ListItem>
      </TouchableOpacity>
    </Swipeable>
  );
};

const styles = StyleSheet.create({
  listItem: {
    borderRadius: 10,
    marginVertical: 8,
    overflow: 'hidden',
  },
  touchable: {
    flex: 1,
    marginHorizontal: 10,
  },
  deleteButton: {
    backgroundColor: 'red',
    justifyContent: 'center',
    alignItems: 'center',
    width: 70,
    height: 'auto',
    marginVertical: 8,
    borderRadius: 10,
  },
});

export default ChatListItem;
